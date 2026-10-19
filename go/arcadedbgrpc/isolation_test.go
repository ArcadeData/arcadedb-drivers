package arcadedbgrpc

import (
	"context"
	"errors"
	"sync"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
)

// isoService records each BeginTransactionRequest's isolation and commits (issue #152).
type isoService struct {
	generated.UnimplementedArcadeDbServiceServer
	mu     sync.Mutex
	begins []generated.TransactionIsolation
}

func (s *isoService) BeginTransaction(_ context.Context, r *generated.BeginTransactionRequest) (*generated.BeginTransactionResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.begins = append(s.begins, r.GetIsolation())
	return &generated.BeginTransactionResponse{TransactionId: "t1"}, nil
}

func (s *isoService) CommitTransaction(context.Context, *generated.CommitTransactionRequest) (*generated.CommitTransactionResponse, error) {
	return &generated.CommitTransactionResponse{Success: true, Committed: true}, nil
}

func (s *isoService) seen() []generated.TransactionIsolation {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]generated.TransactionIsolation(nil), s.begins...)
}

func noop(*TxHandle) error { return nil }

func TestTransactionSendsIsolationLevel(t *testing.T) {
	s := &isoService{}
	c := newFake(t, s, nil)
	ctx := context.Background()
	if err := c.Transaction(ctx, "d", noop, WithIsolationLevel(RepeatableRead)); err != nil {
		t.Fatal(err)
	}
	if err := c.Transaction(ctx, "d", noop, WithIsolationLevel(ReadCommitted)); err != nil {
		t.Fatal(err)
	}
	if err := c.Transaction(ctx, "d", noop); err != nil {
		t.Fatal(err)
	}
	got := s.seen()
	want := []generated.TransactionIsolation{
		generated.TransactionIsolation_REPEATABLE_READ,
		generated.TransactionIsolation_READ_COMMITTED,
		generated.TransactionIsolation_READ_UNCOMMITTED, // unset: proto3's zero value
	}
	if len(got) != len(want) || got[0] != want[0] || got[1] != want[1] || got[2] != want[2] {
		t.Fatalf("isolation sent = %v, want %v", got, want)
	}
}

func TestTransactionRefusesUnknownIsolationLevelUnsent(t *testing.T) {
	s := &isoService{}
	c := newFake(t, s, nil)
	ran := false
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { ran = true; return nil }, WithIsolationLevel("SERIALIZABLE"))
	if !errors.Is(err, ErrInvalidIsolationLevel) || ran || len(s.seen()) != 0 {
		t.Fatalf("err = %v, ran = %v, begins = %v", err, ran, s.seen())
	}
}

func TestTransactionRefusesEmptyIsolationLevelUnsent(t *testing.T) {
	s := &isoService{}
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", noop, WithIsolationLevel(""))
	if !errors.Is(err, ErrInvalidIsolationLevel) || len(s.seen()) != 0 {
		t.Fatalf("err = %v, begins = %v", err, s.seen())
	}
}
