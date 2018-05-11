        if ((beresp.status == 200 || beresp.status == 404) && (beresp.http.content-type ~ "(\+json)\s*($|;)" || req.url ~ "\.(css|js|html|eot|ico|otf|ttf|json|svg)($|\?)" ) ) {
          # always set vary to make sure uncompressed versions dont always win
          if (!beresp.http.Vary ~ "Accept-Encoding") {
            if (beresp.http.Vary) {
              set beresp.http.Vary = beresp.http.Vary ", Accept-Encoding";
            } else {
              set beresp.http.Vary = "Accept-Encoding";
            }
          }
          if (req.http.Accept-Encoding == "gzip") {
            set beresp.gzip = true;
          }
        }
