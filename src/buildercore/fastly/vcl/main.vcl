sub vcl_recv {
  if (req.restarts < 1) {
    # Sanitise header
    unset req.http.X-eLife-Restart;
  }

  # Disable Stale-While-Revalidate if a shield request to avoid double SWR
  if (req.http.Fastly-FF) {
    set req.max_stale_while_revalidate = 0s;
  }

  #FASTLY recv

  if (req.request != "HEAD" && req.request != "GET" && req.request != "FASTLYPURGE") {
    return(pass);
  }

  return(lookup);
}

sub vcl_fetch {
  #FASTLY fetch

  if (beresp.status >= 500 && beresp.status < 600) {
    if (stale.exists) {
      return(deliver_stale);
    }

    if (req.restarts < 1 && (req.request == "GET" || req.request == "HEAD")) {
      set req.http.X-eLife-Restart = "fetch," beresp.status;
      unset req.http.Cookie; # Temporarily log out the user

      restart;
    }

    if (!beresp.http.Content-Length || beresp.http.Content-Length == "0") {
      # Elastic Load Balancer returns empty error responses
      error beresp.status;
    }
  }

  if (req.restarts > 0) {
    set beresp.http.Fastly-Restarts = req.restarts;
  }

  if (beresp.http.Set-Cookie) {
    set req.http.Fastly-Cachetype = "SETCOOKIE";
    return(pass);
  }

  if (beresp.http.Cache-Control ~ "private") {
    set req.http.Fastly-Cachetype = "PRIVATE";
    return(pass);
  }

  if (beresp.status == 500 || beresp.status == 503) {
    set req.http.Fastly-Cachetype = "ERROR";
    set beresp.ttl = 1s;
    set beresp.grace = 5s;
    return(deliver);
  }

  if (beresp.http.Expires || beresp.http.Surrogate-Control ~ "max-age" || beresp.http.Cache-Control ~ "(s-maxage|max-age)") {
    # keep the ttl here
  } else {
    # apply the default ttl
    set beresp.ttl = 3600s;
  }

  return(deliver);
}

sub vcl_hit {
  #FASTLY hit

  if (!obj.cacheable) {
    return(pass);
  }
  return(deliver);
}

sub vcl_miss {
  #FASTLY miss
  return(fetch);
}

sub vcl_deliver {
  if (resp.status >= 500 && resp.status < 600 && stale.exists) {
    set req.http.X-eLife-Restart = "deliver," resp.status;

    restart;
  }

  if (req.http.Fastly-Debug && req.http.X-eLife-Restart) {
    set resp.http.X-eLife-Restart = req.http.X-eLife-Restart;
  }

  #FASTLY deliver
  return(deliver);
}

sub vcl_error {
  if (obj.status >= 500 && obj.status < 600 && stale.exists) {
    return(deliver_stale);
  }

  #FASTLY error
}

sub vcl_pass {
  #FASTLY pass
}

sub vcl_log {
  #FASTLY log
}
