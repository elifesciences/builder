# not to be used directly as a VCL snippet

if (obj.status == ${code}) {
   set obj.http.Content-Type = "text/html; charset=us-ascii";
      synthetic {"${synthetic_response}"};
     return(deliver);
}
