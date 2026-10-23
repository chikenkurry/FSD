package integration

import (
	"testing"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

func TestValidEventWhen(t *testing.T) {
	cases := []struct {
		date, clock string
		ok          bool
	}{
		{"", "", true},
		{"2027-06-02", "", true},
		{"2027-06-02", "19:30", true},
		{"", "19:30", false},
		{"2027-02-30", "", false},
		{"02/06/2027", "", false},
		{"2027-06-02", "24:00", false},
		{"2027-06-02", "7pm", false},
	}
	for _, c := range cases {
		if got := validEventWhen(confirmationRequest{EventDate: c.date, EventTime: c.clock}); got != c.ok {
			t.Errorf("validEventWhen(%q, %q) = %v, want %v", c.date, c.clock, got, c.ok)
		}
	}
}

func TestSelectionRetryMustRepeatTheChosenDate(t *testing.T) {
	op := uuid.New()
	stored := Selection{OperationID: op, RunID: "run", CandidateID: "a",
		Details: datatypes.JSON(`{"event_date":"2027-06-02","event_time":"19:00"}`)}
	same := confirmationRequest{OperationID: op, RunID: "run", CandidateID: "a", EventDate: "2027-06-02", EventTime: "19:00"}
	if !selectionMatches(stored, same) {
		t.Fatal("an identical retry should match the stored selection")
	}
	other := same
	other.EventDate = "2027-06-03"
	if selectionMatches(stored, other) {
		t.Fatal("a retry with a different date must not silently reuse the stored selection")
	}
	undated := Selection{OperationID: op, RunID: "run", CandidateID: "a", Details: datatypes.JSON(`{}`)}
	if !selectionMatches(undated, confirmationRequest{OperationID: op, RunID: "run", CandidateID: "a"}) {
		t.Fatal("selections without dates keep matching as before")
	}
}
