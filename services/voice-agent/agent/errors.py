from __future__ import annotations


class VoiceAgentError(RuntimeError):
    """Base class for safe voice-agent errors."""


class ConfigurationError(VoiceAgentError):
    pass


class InternalAPIAuthenticationError(VoiceAgentError):
    pass


class InternalAPIContractError(VoiceAgentError):
    pass


class InternalAPIPermanentError(InternalAPIContractError):
    """Kalıcı 4xx sözleşme reddi (400/404/422 gibi, veya bozuk/uyumsuz yanıt
    gövdesi). Aynı payload'la tekrar denemek sonucu DEĞİŞTİRMEZ — retry
    edilmemeli. `InternalAPIContractError`'ın alt sınıfı olduğu için onu
    yakalayan mevcut genel `except` blokları (ör. events.py/transcript.py)
    bu sınıfı da kapsamaya devam eder."""


class InternalAPITransientError(InternalAPIContractError):
    """`api_client.py`'nin kendi iç retry bütçesi (timeout/connection-reset/
    429/5xx için) TÜKENDİKTEN SONRA fırlatılır. Üst katman (ör.
    `CompletionGuard`) daha uzun vadeli, ayrı bir retry penceresi
    deneyebilir — aksine `InternalAPIPermanentError` asla yeniden
    denenmemelidir."""


class CallNotDialableError(VoiceAgentError):
    pass


# Standart SIP yanıt kodlarından (RFC 3261) türetilen, protokol düzeyinde
# genel-geçer bir sınıflandırma. LiveKit'e veya Netgsm'e özel bir varsayım
# İÇERMEZ; yalnız `sip_status_code` mevcutsa kullanılır, yoksa "unknown"a düşer.
SIP_FAILURE_REASONS = frozenset(
    {
        "busy",
        "no_answer",
        "rejected",
        "cancelled",
        "authentication_error",
        "trunk_error",
        "redirect_unsupported",
        "unknown_sip_failure",
    }
)


def classify_sip_status(status_code: int | None) -> str:
    """SIP durum kodunu (varsa) genel bir hata nedenine eşler.

    Kaynak: RFC 3261 §21 (standart SIP yanıt kodları). LiveKit/Netgsm'e özel
    hiçbir varsayım yapılmaz; yalnız protokolün kendi anlamları kullanılır.
    """
    if status_code is None:
        return "unknown_sip_failure"
    if status_code == 486:  # Busy Here
        return "busy"
    if status_code in (480, 408):  # Temporarily Unavailable / Request Timeout
        return "no_answer"
    if status_code == 603:  # Decline
        return "rejected"
    if status_code == 487:  # Request Terminated
        return "cancelled"
    if status_code in (401, 403, 407):  # Unauthorized / Forbidden / Proxy Auth Required
        return "authentication_error"
    if 500 <= status_code < 600:
        return "trunk_error"
    if 300 <= status_code < 400:
        return "redirect_unsupported"
    return "unknown_sip_failure"


class SIPParticipantError(VoiceAgentError):
    def __init__(
        self,
        message: str,
        *,
        sip_status_code: int | None = None,
        sip_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.sip_status_code = sip_status_code
        self.sip_status = sip_status
        self.reason = classify_sip_status(sip_status_code)


class SIPTimeoutError(SIPParticipantError):
    """SIP participant oluşturma zaman aşımına uğradı (yanıt hiç gelmedi)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.reason = "timeout"


class RealtimeSessionError(VoiceAgentError):
    pass


class ToolExecutionError(VoiceAgentError):
    pass


class TranscriptDeliveryError(VoiceAgentError):
    pass


class UsageDeliveryError(VoiceAgentError):
    pass


class CompletionError(VoiceAgentError):
    pass
