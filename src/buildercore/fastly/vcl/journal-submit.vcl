if (req.url.path == "/submit") {
    if (std.prefixof(req.http.Referer, "https://staging--xpub.elifesciences.org/")) {
        return(pass);
    }

    if (randomint(1, 100) <= 10) {
      set req.http.X-eLife-Redirect = "https://staging--xpub.elifesciences.org/login";
    } else {
      set req.http.X-eLife-Redirect = "https://submit.elifesciences.org/cgi-bin/main.plex";
    }
    error 302;
}
