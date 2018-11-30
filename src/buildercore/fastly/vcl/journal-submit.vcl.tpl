if (req.url.path == "/submit") {
    if (req.http.Referer ~ "${referer}") {
        return(pass);
    }

    if (randomint(1, 100) <= ${percentage}) {
      set req.http.X-eLife-Redirect = "${xpub_uri}";
    } else {
      set req.http.X-eLife-Redirect = "https://submit.elifesciences.org/cgi-bin/main.plex";
    }
    error 302;
}
