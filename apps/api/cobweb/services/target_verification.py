"""Target ownership verification.

Two methods:
1. **HTTP file**: GET <base_url>/.well-known/cobweb-challenge → body must equal verification_token
2. **Meta tag**: GET <base_url>/ → response HTML contains <meta name="cobweb-site-verification" content="<token>">

Either passing flips the target to VERIFIED.
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx

from cobweb.models.target import Target


class VerificationError(ValueError):
    pass


async def verify_target(target: Target, *, timeout_s: float = 5.0) -> str:
    """Returns the method that succeeded, or raises VerificationError."""
    if not target.verification_token:
        raise VerificationError("No verification token issued")

    token = target.verification_token
    base = target.base_url if target.base_url.endswith("/") else target.base_url + "/"

    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        # Method 1: well-known file
        challenge_url = urljoin(base, ".well-known/cobweb-challenge")
        try:
            r = await client.get(challenge_url)
            if r.status_code == 200 and r.text.strip() == token:
                return "well_known_file"
        except httpx.HTTPError:
            pass

        # Method 2: meta tag in homepage
        try:
            r = await client.get(base)
            if r.status_code == 200 and _meta_match(r.text, token):
                return "meta_tag"
        except httpx.HTTPError as e:
            raise VerificationError(f"Could not reach target: {e}") from e

    raise VerificationError(
        "Verification failed. Place file at /.well-known/cobweb-challenge or "
        "add <meta name='cobweb-site-verification' content='...'> to the homepage."
    )


def _meta_match(html: str, token: str) -> bool:
    needle = f'name="cobweb-site-verification" content="{token}"'
    return needle in html or needle.replace('"', "'") in html
