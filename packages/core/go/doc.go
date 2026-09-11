// Package stellar_lense provides an idiomatic Go client for the Stellar Lense
// fraud-detection REST API.
//
// # Usage
//
//	client := stellar_lense.NewClient("https://api.stellar-lense.io",
//	    stellar_lense.WithAPIKey("your-api-key"),
//	)
//	resp, err := client.GetScore(ctx, wallet)
//	if err != nil { return err }
//	for _, s := range resp.Scores {
//	    if s.Score >= 70 && s.MLFlag {
//	        return fmt.Errorf("withdrawal blocked: risk score %d", s.Score)
//	    }
//	}
//
// # Webhook verification
//
//	ok := stellar_lense.VerifyWebhookSignature(body, secret, r.Header.Get("X-StellarLense-Signature"))
//	if !ok {
//	    http.Error(w, "invalid signature", http.StatusUnauthorized)
//	    return
//	}
//	ok = stellar_lense.VerifyWebhookTimestamp(r.Header.Get("X-StellarLense-Timestamp"), 5*time.Minute)
//
// # Struct types
//
// All structs intentionally mirror (but do not import from) detection/risk_score.py
// and the Python SDK models. Keep them in sync with the cross-repo contract
// described in the root README's "Stellar Lense Organization" section.
package stellar_lense
