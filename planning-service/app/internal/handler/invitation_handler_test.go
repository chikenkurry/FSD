package handler

import (
	"net/url"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestInvitationLinkOpensTheRoundInTheFrontend(t *testing.T) {
	round := uuid.New()
	for _, appURL := range []string{"https://what2do.example.com", "https://what2do.example.com/"} {
		link := invitationLink(appURL, round, "a1b2c3")
		prefix := "https://what2do.example.com/#"
		if !strings.HasPrefix(link, prefix) {
			t.Fatalf("link %q does not open the frontend root", link)
		}
		// The frontend reads the round and invitation from the hash (services/invite.ts).
		params, err := url.ParseQuery(strings.TrimPrefix(link, prefix))
		if err != nil || params.Get("round") != round.String() || params.Get("invite") != "a1b2c3" {
			t.Fatalf("link %q does not carry the round and invitation", link)
		}
	}
}

func TestInvitationLinkEscapesTheToken(t *testing.T) {
	link := invitationLink("http://localhost:15173", uuid.New(), "a&b=c")
	params, _ := url.ParseQuery(link[strings.Index(link, "#")+1:])
	if params.Get("invite") != "a&b=c" {
		t.Fatalf("token was not escaped: %q", link)
	}
}
