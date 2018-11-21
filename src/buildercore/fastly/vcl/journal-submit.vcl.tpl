if (req.url.path == "/submit") {
    if (std.prefixof(req.http.Referer, "${xpub_uri}")) {
        return(pass);
    }

    if (randomint(1, 100) <= 10) {
      set req.http.X-eLife-Redirect = "${xpub_uri}login";
    } else {
      set req.http.X-eLife-Redirect = "https://submit.elifesciences.org/cgi-bin/main.plex";
    }
    error 302;
}
