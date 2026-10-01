package arcadedb

import (
	"encoding/base64"
	"net/http"
)

// Go has neither of the JavaScript btoa hazards (it rejects code points above U+00FF), so
// credentials are UTF-8 encoded straight into the header with no pre-encoding step.

func basicAuthValue(user, password string) string {
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(user+":"+password))
}

func bearerAuthValue(token string) string { return "Bearer " + token }

// applyHeaders sets every configured header on h, replacing any existing value.
func applyHeaders(h http.Header, headers map[string]string) {
	for k, v := range headers {
		h.Set(k, v)
	}
}
