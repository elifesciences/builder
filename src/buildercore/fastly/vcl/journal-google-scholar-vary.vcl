if (!req.http.Fastly-FF && !req.http.Fastly-Debug) {
    set resp.http.Vary = regsub(resp.http.Vary, ",?\s*X-eLife-Google-Scholar-Metadata\s*", "");
    set resp.http.Vary = regsub(resp.http.Vary, "^[,\s]+", "");
    if (resp.http.Vary == "") {
        unset resp.http.Vary;
    }
}
