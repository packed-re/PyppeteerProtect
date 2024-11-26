import asyncio;
import secrets;
import string;

from pyppeteer.launcher import DEFAULT_ARGS;

def SetSecureArguments():
	if("--disable-blink-features=AutomationControlled" not in DEFAULT_ARGS):
		DEFAULT_ARGS.append("--disable-blink-features=AutomationControlled");

	DEFAULT_ARGS.remove("--enable-automation");

def _IndexArgs(args, kwargs, index, keyword): # we need this to ensure compatability with further versions of pyppeteer, incase the functions we hook gain/lose an argument
	kwVal = kwargs.get(keyword);

	if(kwVal is None):
		return args[index];
	else:	
		return kwVal;

_hook_return_none = object();
def _CreateHook(orig_func, new_func):
	def hook(*args, **kwargs):
		out = new_func(orig_func, *args, **kwargs);

		if(out is not None):
			if(out is _hook_return_none):
				return None;
			else:
				return out;

		return orig_func(*args, **kwargs);
	
	return hook;

_userAgent = None; # ensured to be the headful version
_userAgentIsHeadless = False;

class _PyppeteerProtect:
	@classmethod
	async def Make(cls, page, useMainContext = False):
		out = cls();

		out.page = page;
		out.executionContext = await page.mainFrame.executionContext();
		out._executionContextPromise = asyncio.Future();
		out.bindingName = "";

		out._useMainContext = useMainContext;

		out._mainWorldContextId = None;
		out._isolatedWorldContextId = None;

		global _userAgent;
		global _userAgentIsHeadless;
		if(_userAgent is None):
			_ua = await out.page.browser.userAgent();
			_userAgentIsHeadless = _ua.find("HeadlessChrome") != -1;
			_userAgent = _ua.replace("HeadlessChrome", "Chrome") if _userAgentIsHeadless else _ua;

		if(_userAgentIsHeadless):
			await page.setUserAgent(_userAgent);

		await out.page._client.send("Runtime.disable", {});
		def SendHook(orig_func, *args, **kwargs):
			if(_IndexArgs(args, kwargs, 0, "method") == "Runtime.enable"):
				print("Runtime.enable request dropped by PyppeteerProtect");
				future = asyncio.Future();
				future.set_result(True);
				return future;

		out.page._client.send = _CreateHook(page._client.send, SendHook);

		baseBindingCalled = page._client.listeners("Runtime.bindingCalled")[0];
		out.page._client._events["Runtime.bindingCalled"][baseBindingCalled] = _CreateHook(baseBindingCalled, out._bindingCalledHook) # there can only be one bindingCalled listener, otherwise the CDP session will hang forever
		
		out.page.on("request", lambda request: asyncio.create_task(out._requestHandler(request)));
		out.page.on("response", lambda response: asyncio.create_task(out._responseHandler(response)));
		
		out.executionContext.evaluateHandle = _CreateHook(out.executionContext.evaluateHandle, out._evaluateHandleHook);

		for i in range(16):
			out.bindingName += secrets.choice(string.ascii_uppercase + string.ascii_lowercase);

		await out.page._client.send("Page.addScriptToEvaluateOnNewDocument", {
			"source": f"document.addEventListener(\"{out.bindingName}\", (e) => self[\"{out.bindingName}\"](\"payload\"))",
			# "runImmediately": True # this shouldnt really ever be done since addEventListener can be hooked and detected
		});

		await out.applyExecutionContext();

		return out

	async def applyExecutionContext(self):
		if(self._useMainContext):
			await self.useMainContext();
		else:
			await self.useIsolatedWorld();

	async def _getIsolatedWorld(self):
		if(self._isolatedWorldContextId is None):
			self._isolatedWorldContextId = (await self.page._client.send('Page.createIsolatedWorld', {
				"frameId": self.page.mainFrame._id,
				"worldName": self.bindingName,
				"grantUniveralAccess": True,
			}))["executionContextId"];

		return self._isolatedWorldContextId;

	async def useIsolatedWorld(self):
		self._useMainContext = False;
		self.executionContext._contextId = await self._getIsolatedWorld();
		if(not self._executionContextPromise.done()):
			self._executionContextPromise.set_result(True);
	
	async def useMainContext(self):
		self._useMainContext = True;
		if (self._mainWorldContextId is None):
			await self.page._client.send("Runtime.addBinding", {
				"name": self.bindingName
			});

			await self.page._client.send("Runtime.evaluate", {
				"expression": f"document.dispatchEvent(new CustomEvent(\"{self.bindingName}\"));",
				"executionContextId": await self._getIsolatedWorld()
			});
		else: # incase the above finishes before bindingCalled gets called
			self.executionContext._contextId = self._mainWorldContextId;

	def waitForExecutionContext(self):
		return self._executionContextPromise;

	def _bindingCalledHook(self, orig_func, *args, **kwargs):
		event = _IndexArgs(args, kwargs, 0, "event");
		if(event["name"] != self.bindingName):
			return;

		self._mainWorldContextId = event["executionContextId"]
		self.executionContext._contextId = self._mainWorldContextId;
		if(not self._executionContextPromise.done()):
			self._executionContextPromise.set_result(True);

		return _hook_return_none;

	async def _evaluateHandleHook(self, orig_func, *args, **kwargs): # there were certain edge cases where the navigation would happen so fast (particularly when loading local html files) that our response listener couldn't fetch an execution context in time, this should fix that
		await self.waitForExecutionContext();

		origReturn = await orig_func(*args, **kwargs);

		if(origReturn is None):
			return _hook_return_none;
		else:
			return origReturn;

	async def _requestHandler(self, request):
		if(request.frame is not self.page.mainFrame): # skip iframes and stuff
			return;

		if(not request._isNavigationRequest):
			return;

		self._executionContextPromise = asyncio.Future();

	async def _responseHandler(self, response):
		if(response.request.frame is not self.page.mainFrame): # skip iframes and stuff
			return;

		if(not response.request._isNavigationRequest):
			return;

		self._mainWorldContextId = None;
		self._isolatedWorldContextId = None;

		await self.applyExecutionContext();

def PyppeteerProtect(*args, **kwargs):
	return _PyppeteerProtect.Make(*args, **kwargs);