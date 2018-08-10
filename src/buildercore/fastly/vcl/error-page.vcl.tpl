if (obj.status ${comparison}) {
    set obj.http.Content-Type = "text/html; charset=us-ascii";
    synthetic {"${synthetic_response}"};
    return(deliver);
}
