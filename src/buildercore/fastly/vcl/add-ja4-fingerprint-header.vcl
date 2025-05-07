# Add JA4 Client Fingerprint to headers
# The condition means that we only set and carry the earliest fingerprint from the edge
if (!req.http.x-ja4fingerprint) {
  set req.http.x-ja4fingerprint = tls.client.ja4;
}
