
import asyncio;
import secrets;
import string;

def _create_hook(orig_func, new_func):
	def hook(*args, **kwargs):
		out = new_func(*args, **kwargs);

		if(out is None):
			return orig_func(*args, **kwargs);
		else:
			return out;
	
	return hook;

_baseBindingHookRemoved = False;
class _PyppeteerProtect:
	@classmethod
	async def Make(cls, page, useMainContext = False):
		out = cls();

		out.page = page;
		out.executionContext = await page.mainFrame.executionContext();
		out.bindingName = "";

		out._useMainContext = useMainContext;

		out._mainWorldInitialized = False;
		out._mainWorldContextId = None;

		out._isolatedWorldContextId = None;

		await out.page._client.send("Runtime.disable", {});
		def SendHook(method, params):
			if(method == "Runtime.enable"):
				print("denying Runtime.enable request");
				future = asyncio.Future();
				future.set_result(True);
				return future;

		out.page._client.send = _create_hook(page._client.send, SendHook);

		global _baseBindingHookRemoved;
		if(_baseBindingHookRemoved is False):
			page._client.remove_listener("Runtime.bindingCalled", page._client.listeners("Runtime.bindingCalled")[0]); # if i dont do this the calls to our binding will make the CDP session hang forever
			_baseBindingHookRemoved = True;
		
		out.page.on("response", lambda response: asyncio.create_task(out._responseHandler(response)));

		for i in range(16):
			out.bindingName += secrets.choice(string.ascii_uppercase + string.ascii_lowercase);

		await out.page._client.send("Page.addScriptToEvaluateOnNewDocument", {
			"source": f"document.addEventListener(\"{out.bindingName}\", (e) => self[\"{out.bindingName}\"](\"payload\"))",
			# "runImmediately": True # this shouldnt really ever be done since addEventListener can be hooked and detected
		});

		await out._ApplyExecutionContext();

		return out

	async def _ApplyExecutionContext(self):
		if(self._useMainContext):
			await self.useMainContext();
		else:
			await self.useIsolatedWorld();

	async def _GetIsolatedWorld(self):
		if(self._isolatedWorldContextId is None):
			self._isolatedWorldContextId = (await self.page._client.send('Page.createIsolatedWorld', {
				"frameId": self.page.mainFrame._id,
				"worldName": self.bindingName,
				"grantUniveralAccess": True,
			}))["executionContextId"];

		return self._isolatedWorldContextId;

	async def useIsolatedWorld(self):
		self._useMainContext = False;
		self.executionContext._contextId = await self._GetIsolatedWorld();
	
	async def useMainContext(self):
		self._useMainContext = True;

		if (self._mainWorldInitialized is False):
			self.page._client.on("Runtime.bindingCalled", self._bindingCalledHandler);
			self._mainWorldInitialized = True;

		if (self._mainWorldContextId is None):
			await self.page._client.send("Runtime.addBinding", {
				"name": self.bindingName
			});

			await self.page._client.send("Runtime.evaluate", {
				"expression": f"document.dispatchEvent(new CustomEvent(\"{self.bindingName}\"));",
				"executionContextId": await self._GetIsolatedWorld()
			});
		else: # incase the above finishes before bindingCalled gets called
			self.executionContext._contextId = self._mainWorldContextId;

	def _bindingCalledHandler(self, event):
		if(event["name"] != self.bindingName):
			return;

		self._mainWorldContextId = event["executionContextId"]
		self.executionContext._contextId = self._mainWorldContextId;

	async def _responseHandler(self, response):
		if(response.request.frame is not self.page.mainFrame): # skip iframes and stuff
			return;

		if(not response.request._isNavigationRequest):
			return;
			
		self._mainWorldContextId = None;
		self._isolatedWorldContextId = None;

		await self._ApplyExecutionContext();

def PyppeteerProtect(*args, **kwargs):
	return _PyppeteerProtect.Make(*args, **kwargs);