declare local var.journal_cookie STRING;
set var.journal_cookie = req.http.Cookie:journal;
if (var.journal_cookie != "") {
    set req.http.Cookie = "journal=" var.journal_cookie ";";
} else {
    unset req.http.Cookie;
}
