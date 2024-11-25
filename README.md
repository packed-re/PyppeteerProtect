# PyppeteerProtect

PyppeterProtect is an implementation of [rebrowser-patches](https://github.com/rebrowser/rebrowser-patches), in pyppeteer. A notable difference, however, is that you don't need to modify your installation of pyppeteer for it to work, you simply call `PyppeteerProtect` on a target page and the patches get applied automatically.

PyppeteerProtect, at the moment, doesn't provide protection for running in headless mode. For this you should look into a library like [pyppeteer_stealth](https://github.com/MeiK2333/pyppeteer_stealth) (though it doesn't really work on any of the major anti-bot solutions, like DataDome, infact it makes you more detectable).

## Install

```
$ pip install PyppeteerProtect
```

## Usage

Import the library:
```python
from PyppeteerProtect import PyppeteerProtect;
```
Protect individual pages:
```python
pageProtect = await PyppeteerProtect(page);
```
Switch between using the main and isolated execution context:
```python
pageProtect.useMainWorld();
pageProtect.useIsolatedWorld();
```

By default, PyppeteerProtect will use the execution context id of an isolated world. This is ideal for ensuring maximum security, as you don't have to worry about calling hooked global functions or accidentally leaking your pressence through global variables, however, it makes the code of the target page inaccessible.

If you plan on using the main world execution context and nothing else, you can configure the PyppeteerProtect constructor to use it on creation like so:
```python
pageProtect = await PyppeteerProtect(page, True);
```
## Example

```python
import asyncio;

from pyppeteer import launch;
from PyppeteerProtect import PyppeteerProtect;

loop = asyncio.new_event_loop();
async def main():
    browser = await launch(
        executablePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        headless = False,
        loop = loop,

        args=["--disable-blink-features=AutomationControlled"] # you need this to remain undetected
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

PyppeteerProtect works by calling `Runtime.disable` and hooking `CDPSession.send` to drop any `Runtime.enable` requests sent by the pyppeteer library. `Runtime.enable` is used to retrieve an execution context id, which is required for functions such as `Page.evaluate` and `Page.querySelectorAll` to work, but in doing so, it enables the scripts running on the target page to observe behavior that would indicate that the browser is being controlled by automation software, like pyppeteer/puppeteer.

PyppeteerProtect retrieves an execution context either by calling out to a binding (created with `Runtime.addBinding` and `Runtime.bindingCalled`, and called using `Page.addScriptToEvaluateOnNewDocument` and `Runtime.evaluate` in an isolated context), or by creating an isolated world (using `Page.createIsolatedWorld`).

These patches are applied automatically on each navigation using `Page.on("response", callback)`.