if (!req.http.Fastly-FF && !req.http.Fastly-Debug) {
    set resp.http.Vary = regsub(resp.http.Vary, "X-eLife-Google-Scholar-Metadata, ", "");
    if (resp.http.Vary ~ "^\s*$") {
        unset resp.http.Vary;
    }
}
