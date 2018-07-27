# Set X-Forwarded-Host if not a shield request
if (!req.http.Fastly-FF) {
  set req.http.X-Forwarded-Host = req.http.host;
}
