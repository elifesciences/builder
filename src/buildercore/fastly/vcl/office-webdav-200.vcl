if(
    req.http.User-Agent ~ "Microsoft Office Protocol Discovery"
    ||
    req.http.User-Agent ~ "Microsoft Office Existence Discovery"
    ||
    req.http.User-Agent ~ "Microsoft-WebDAV-MiniRedir"
    ||
    req.http.User-Agent ~ "^Microsoft Office (Excel|PowerPoint|Word)"
    ||
    (req.http.User-Agent ~ "ms-office" && req.http.User-Agent !~ "Microsoft Outlook")
) {
    error 200;
}
