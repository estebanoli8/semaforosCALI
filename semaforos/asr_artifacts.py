"""Known ASR boilerplate that must not become a citizen finding.

The literal transcript remains stored for audit.  These helpers only decide what
can continue to semantic analysis and report projection.
"""
import re
import unicodedata


def normalized(text):
    value=unicodedata.normalize('NFKD',text or '')
    value=''.join(char for char in value if not unicodedata.combining(char))
    return ' '.join(re.sub(r'[^a-z0-9.]+',' ',value.casefold()).split())


def artifact_reason(text):
    """Return a stable reason only for high-precision, known boilerplate."""
    value=normalized(text)
    if not value:
        return None
    if 'amara.org' in value and ('subtitul' in value or len(value)<=80):
        return 'subtitle_credit_amara'
    if re.fullmatch(r'(?:por favor )?suscribete(?: (?:a|al) (?:mi |nuestro |este )?canal)?[.!]?',value):
        return 'subscription_outro'
    return None


def is_artifact(text):
    return artifact_reason(text) is not None
