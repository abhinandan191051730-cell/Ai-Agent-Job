class SelectorNotFoundError(Exception):
    def __init__(self, element_name: str, selectors_tried: list, page_url: str = ""):
        self.element_name = element_name
        self.selectors_tried = selectors_tried
        self.page_url = page_url
        url_suffix = f" at {page_url}" if page_url else ""
        super().__init__(
            f"Critical element '{element_name}' not found{url_suffix}. "
            f"Tried selectors: {selectors_tried}"
        )


class AuthRequiredError(Exception):
    def __init__(self, platform: str):
        self.platform = platform
        super().__init__(f"Authentication required for {platform} — log in via the browser profile first")


class CaptchaThresholdExceeded(Exception):
    def __init__(self, platform: str, count: int, threshold: int):
        self.platform = platform
        self.count = count
        self.threshold = threshold
        super().__init__(f"CAPTCHA threshold exceeded for {platform}: {count}/{threshold}")
