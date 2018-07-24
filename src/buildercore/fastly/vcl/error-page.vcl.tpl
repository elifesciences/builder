if (obj.status == ${code}) {
  if (stale.exists) {
    return(deliver_stale);
  }

  set obj.http.Content-Type = "text/html; charset=us-ascii";
  synthetic {"${synthetic_response}"};

  return(deliver);
}
