if (req.http.User-Agent ~ "Googlebot/") {
    set req.http.X-eLife-Google-Scholar-Metadata = "1";
} else {
    unset req.http.X-eLife-Google-Scholar-Metadata;
}
