> Supplied background document. For the combined build, INTEGRATION_NOTES.md and VALIDATION.md supersede conflicting API, limit, or test details below.

# Research Gap

## Existing Solutions
Resumable uploads are well-established:
- **[tus protocol](https://tus.io/)** - Open protocol for resumable file uploads, widely used
- **[IETF HTTP Resumable Uploads Draft](https://datatracker.ietf.org/doc/draft-ietf-httpbis-resumable-upload/)** - Standardization effort for resumable uploads in HTTP

Rate limiting is a standard technique with many implementations (token bucket, sliding window, leaky bucket).

## Our Contribution
Our contribution is a small, testable engineering idea:

**Separating new-session admission from continuation of authorized sessions in a deadline setting.**

Specifically:
1. **Admission control separation**: Only the creation of a NEW upload session counts against a strict rate limit (3 per minute). Once a session is authorized and created, all continuation operations (uploading chunks, checking status, finalizing) are not charged against this limit.
2. **Deadline-aware session handling**: New sessions are only allowed before the deadline (server-enforced). Existing sessions may continue and finalize within a faculty-configured recovery window after the deadline.
3. **Measurable effect**: The comparison script demonstrates that this approach allows honest students to complete interrupted uploads (even with retries) while still preventing abuse of session creation endpoints.

This is not a novel protocol or algorithm, but a practical engineering design choice applied to the specific context of assignment submissions with hard deadlines. The effect is measurable and testable as shown in our comparison script.

## Limitations of This Contribution
- Only addresses session creation abuse, not other attack vectors
- Recovery window is a policy decision, not cryptographic proof of timeliness
- Implementation is specific to this use case
