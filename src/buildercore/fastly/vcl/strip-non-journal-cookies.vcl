declare local var.journal_cookie STRING;
set var.journal_cookie = req.http.Cookie:journal;
if (var.journal_cookie != "" && req.url.path !~ "^/assets/") {
    set req.http.Cookie = "journal=" var.journal_cookie ";";
    return(pass);
} else {
    unset req.http.Cookie;
}
