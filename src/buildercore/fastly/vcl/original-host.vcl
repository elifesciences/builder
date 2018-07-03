if (!req.http.Fastly-FF) {
  set req.http.X-Forwarded-Host = req.http.host;
}
