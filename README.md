# PyppeteerProtect

PyppeterProtect is an implementation of [rebrowser-patches](https://github.com/rebrowser/rebrowser-patches), in pyppeteer, with the notable difference of not requiring you to modify your installation of pyppeteer for it to work. You simply call `PyppeteerProtect` on a target page and the patches get applied automatically.

PyppeteerProtect (at the moment) doesn't provide protection for running in headless mode, besides a simple set of the useragent to remove `HeadlessChrome`. For this you should look into finding an additional library that you can run over PyppeteerProtect that can offer such protections, like [pyppeteer_stealth](https://github.com/MeiK2333/pyppeteer_stealth), for example (though this specifically, only makes you more detectable for the major anti-bot solutions).

## Installation

```
pip install PyppeteerProtect
```

## Usage

Import the library:
```python
from PyppeteerProtect import PyppeteerProtect, SetSecureArguments;
```
Set default arguments for the chrome executable that help stay protected (sets `--disable-blink-features=AutomationControlled` and removes `--enable-automation`) 
```python
SetSecureArguments(); # should be called before pyppeteer.launch
```

Protect individual pages:
```python
pageProtect = await PyppeteerProtect(page);
```
### Execution contexts
Switch between using the main and isolated execution context:
```python
await pageProtect.useMainWorld();
await pageProtect.useIsolatedWorld();
```

By default, PyppeteerProtect will use the execution context id of an isolated world. This is ideal for ensuring maximum security, as you don't have to worry about calling hooked global functions or accidentally leaking your pressence through global variables, however, it makes the code of the target page inaccessible.

If you plan on using the main world execution context and nothing else, you can configure the PyppeteerProtect constructor to use it on creation like so:
```python
pageProtect = await PyppeteerProtect(page, True);
```

### Special use cases
You are freely able to swap between each of the contexts during active sessions. As an example, you might want to do something like this:
```python
await pageProtect.useIsolatedWorld();
token = await page.evaluate("() => document.querySelector('input[type=\'hidden\']#embedded-token')"); # document.querySelector might have been hooked in the main world to block queries for #embedded-token
await pageProtect.useMainWorld();
data = await page.evaluate("(token) => window.get_some_data(token)", token);
```

If you have a particularly special use case and are having issues with automatically obtaining an execution context id, you can use PyppeteerProtect to wait until one is obtained (though if you stick to basic `Page.evaluate` calls, this isn't something you should be worried about, as it gets called automatically)
```python
await pageProtect.waitForExecutionContext();
```

## Example

```python
import asyncio;

from pyppeteer import launch;
from PyppeteerProtect import PyppeteerProtect, SetSecureArguments;

SetSecureArguments(); # set --disable-blink-features=AutomationControlled and remove --enable-automation

loop = asyncio.new_event_loop();
async def main():
    browser = await launch(
        executablePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        headless = False, # currently no protection for running headless
        defaultViewport = {"width": 1920, "height": 953},
        loop = loop
    );

    page = (await browser.pages())[0];
    pageProtect = await PyppeteerProtect(page);
	
    await page.goto("https://www.datadome.co");
    print(await page.evaluate("()=>'Test Output'"));

    await asyncio.sleep(5000);
    await browser.close();

loop.run_until_complete(main());
```

## How does it works?

PyppeteerProtect works by calling `Runtime.disable` and hooking `CDPSession.send` to drop any `Runtime.enable` requests sent by the pyppeteer library. `Runtime.enable` is used to retrieve an execution context id, which is required for functions such as `Page.evaluate` and `Page.querySelectorAll` to work, but in doing so, it enables the scripts running on the target page to observe behavior that would indicate the browser is being controlled by automation software, like pyppeteer/puppeteer.

PyppeteerProtect retrieves an execution context either by calling out to a binding (created with `Runtime.addBinding` and `Runtime.bindingCalled`, and called using `Page.addScriptToEvaluateOnNewDocument` and `Runtime.evaluate` in an isolated context), or by creating an isolated world (using `Page.createIsolatedWorld`).

These patches are applied automatically on each navigation by listening to the `request` and `response` events of the page, and by hooking `ExecutionContext.evaluateHandle` to explicitly wait for an execution context to be obtained, incase one hasn't been retrieved in time.