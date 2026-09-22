"""Optional Playwright helper.

対象ページのレスポンスから verify-related data を拾うための小さい helper です。
"""

from __future__ import annotations


class BrowserVT:
    """Playwright で対象レスポンスを監視します。"""

    def __init__(self, signup_url: str, email_selector: str = 'input[type="email"]',
                 submit_text: str = "Send", intercept_substring: str = "geeTestForm",
                 vt_path=("data", "verifyType"), lot_path=("data", "verifyLot"),
                 headless: bool = True, timeout: int = 30000):
        self.signup_url = signup_url
        self.email_selector = email_selector
        self.submit_text = submit_text
        self.intercept_substring = intercept_substring
        self.vt_path = tuple(vt_path)
        self.lot_path = tuple(lot_path)
        self.headless = headless
        self.timeout = timeout

    @staticmethod
    def _dig(obj, path):
        """nested dict を path でたどります。"""
        for k in path:
            obj = obj[k]
        return obj

    def get_vt_for(self, identifier: str) -> tuple[str, str]:
        """ページを操作して (verifyType, verifyLot) を取得します。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError("playwright が要ります: pip install playwright") from e
        captured: dict = {}
        with sync_playwright() as p:
            # webdriver flag を出さない設定で起動
            browser = p.chromium.launch(headless=self.headless,
                                        args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context()
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            def on_resp(resp):
                try:
                    if self.intercept_substring in resp.url:
                        captured["json"] = resp.json()
                except Exception:
                    pass
            page.on("response", on_resp)
            page.goto(self.signup_url)
            page.fill(self.email_selector, identifier)
            page.get_by_text(self.submit_text, exact=False).first.click()
            page.wait_for_function(
                f"!!document.body.innerText",
                timeout=self.timeout)
            import time
            t0 = time.time()
            while "json" not in captured and time.time() - t0 < self.timeout / 1000:
                time.sleep(0.2)
            browser.close()
        if "json" not in captured:
            raise RuntimeError(f"{self.intercept_substring!r} を含むレスポンスを拾えませんでした")
        j = captured["json"]
        return self._dig(j, self.vt_path), self._dig(j, self.lot_path)
