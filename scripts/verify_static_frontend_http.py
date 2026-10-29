"""Verify real static frontend redirects behind a mapped HTTP port."""

import argparse
import json
from urllib import error, parse, request


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def verify(base_url: str) -> dict:
    parsed = parse.urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Expected an HTTP origin without credentials")
    origin = base_url.rstrip("/")
    opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
    results = []
    cases = (
        ("/", "/data_copilot/"),
        ("/data_copilot", "/data_copilot/"),
        ("/data_copilot/login", "/data_copilot/login/"),
        (
            "/data_copilot/login?redirect_probe=1",
            "/data_copilot/login/?redirect_probe=1",
        ),
        (
            "/data_copilot?threadId=00000000-0000-4000-8000-000000000001",
            "/data_copilot/?threadId=00000000-0000-4000-8000-000000000001",
        ),
    )
    for path, expected in cases:
        url = origin + path
        try:
            response = opener.open(url, timeout=5)
        except error.HTTPError as exc:
            response = exc
        with response:
            location = response.headers.get("Location", "")
            if response.status not in (301, 302, 307, 308) or not location:
                raise RuntimeError(f"{path}: expected a redirect")
            if parse.urljoin(url, location) != origin + expected:
                raise RuntimeError(
                    f"{path}: redirect changed origin, port, path or query: {location}"
                )
            results.append({"path": path, "status": response.status, "location": location})
    for path in ("/data_copilot/", "/data_copilot/login/"):
        with opener.open(origin + path, timeout=5) as response:
            if response.status != 200 or (
                response.headers.get_content_type() != "text/html"
            ):
                raise RuntimeError(f"{path}: static page did not return HTML 200")
            results.append({"path": path, "status": response.status})
    return {"status": "passed", "transport": "TCP HTTP", "checks": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
