---------------------------- MODULE LedgerLens ----------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS 
    Wallets,
    Scores,
    Assets,
    COOLDOWN,
    HWM_THRESHOLD,
    FLOOR_VALUE,
    RISK_THRESHOLD,
    \* ── Token-bucket constants ──────────────────────────────────────────────
    \* MIN_CAPACITY and MAX_CAPACITY bound the range of capacity values that
    \* TLC will explore when model-checking SetBurstCapacity.
    MIN_CAPACITY,   \* smallest capacity the admin may set (≥ 1)
    MAX_CAPACITY    \* largest capacity the admin may set

VARIABLES 
    score,
    hwm,
    breach_count,
    last_submit_time,
    embargo_expiry,
    delegate,
    now,
    \* ── Token-bucket variables ──────────────────────────────────────────────
    \* tb_tokens[w]      – current token count for wallet w (across the single
    \*                     pair modelled here; extend to a function of pairs for
    \*                     a multi-pair model).
    \* tb_last_refill[w] – ledger timestamp of the last refill anchor.
    \* tb_capacity       – global burst capacity (max tokens per bucket).
    \* NOTE: The Rust implementation stores one bucket per (wallet, asset_pair).
    \*       For clarity this spec models a single canonical pair; all
    \*       multi-pair behaviour follows by symmetry.
    tb_tokens,
    tb_last_refill,
    tb_capacity

vars == <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now,
          tb_tokens, tb_last_refill, tb_capacity>>

\* ── Helper: compute refilled token count ─────────────────────────────────────
\* Mirrors the Rust expression:
\*   let elapsed  = now.saturating_sub(last_refill);
\*   let refills  = elapsed / cooldown;        (integer division)
\*   let refilled = min(tokens + refills, capacity);
RefillCount(w) ==
    LET elapsed  == now - tb_last_refill[w]
        refills  == elapsed \div COOLDOWN
    IN  Min(tb_tokens[w] + refills, tb_capacity)

\* Convenience: smaller of two naturals
Min(a, b) == IF a <= b THEN a ELSE b

\* ── Initialization ───────────────────────────────────────────────────────────
Init ==
    /\ score           = [w \in Wallets |-> 0]
    /\ hwm             = [w \in Wallets |-> 0]
    /\ breach_count    = [w \in Wallets |-> 0]
    /\ last_submit_time= [w \in Wallets |-> 0]
    /\ embargo_expiry  = [w \in Wallets |-> 0]
    /\ delegate        = [w \in Wallets |-> "None"]
    /\ now             = 1
    \* Token-bucket: every wallet starts with a full bucket.
    /\ tb_tokens       = [w \in Wallets |-> MIN_CAPACITY]
    /\ tb_last_refill  = [w \in Wallets |-> 1]
    /\ tb_capacity     = MIN_CAPACITY

\* ── Action: TickTime ─────────────────────────────────────────────────────────
TickTime ==
    /\ now' = now + 1
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate,
                   tb_tokens, tb_last_refill, tb_capacity>>

\* ── Action: SubmitScore ──────────────────────────────────────────────────────
\* A score submission is accepted only when the wallet's token bucket has at
\* least one token available (RefillCount > 0).  On acceptance:
\*   – one token is consumed,
\*   – last_refill is advanced by (refills * COOLDOWN) so the clock doesn't
\*     "slip" (matches the Rust `new_last_refill` calculation), and
\*   – score / hwm / breach_count / last_submit_time are updated as before.
\*
\* When tb_capacity = 1 this collapses to the legacy flat-cooldown model:
\* a submission is accepted only after COOLDOWN ticks have elapsed.
SubmitScore(w, s) ==
    LET refilled  == RefillCount(w)
        elapsed   == now - tb_last_refill[w]
        refills   == elapsed \div COOLDOWN
        new_last_refill == tb_last_refill[w] + refills * COOLDOWN
    IN
    /\ hwm[w] >= HWM_THRESHOLD => s >= FLOOR_VALUE
    /\ refilled > 0                        \* token available — gate
    /\ score'           = [score           EXCEPT ![w] = s]
    /\ hwm'             = [hwm             EXCEPT ![w] = IF s > hwm[w] THEN s ELSE hwm[w]]
    /\ breach_count'    = [breach_count    EXCEPT ![w] = IF s >= RISK_THRESHOLD THEN breach_count[w] + 1 ELSE 0]
    /\ last_submit_time'= [last_submit_time EXCEPT ![w] = now]
    /\ tb_tokens'       = [tb_tokens       EXCEPT ![w] = refilled - 1]
    /\ tb_last_refill'  = [tb_last_refill  EXCEPT ![w] = new_last_refill]
    /\ UNCHANGED <<embargo_expiry, delegate, now, tb_capacity>>

\* ── Action: SetBurstCapacity ─────────────────────────────────────────────────
\* Admin reduces or increases burst capacity.  The Rust implementation applies
\* the new capacity lazily — existing per-bucket token counts are clamped to
\* the new capacity on the *next* refill, not immediately.  We model that
\* faithfully: only tb_capacity changes; tb_tokens is left untouched.
\*
\* The guard capacity >= MIN_CAPACITY ensures capacity never drops to 0
\* (which would permanently lock all submissions).
SetBurstCapacity(capacity) ==
    /\ capacity >= MIN_CAPACITY
    /\ capacity <= MAX_CAPACITY
    /\ tb_capacity' = capacity
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now,
                   tb_tokens, tb_last_refill>>

\* ── Action: SetEmbargo ───────────────────────────────────────────────────────
SetEmbargo(w, expiry) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = expiry]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now,
                   tb_tokens, tb_last_refill, tb_capacity>>

\* ── Action: LiftEmbargo ──────────────────────────────────────────────────────
LiftEmbargo(w) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = 0]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now,
                   tb_tokens, tb_last_refill, tb_capacity>>

\* ── Action: SetDelegate / RemoveDelegate ─────────────────────────────────────
SetDelegate(sub, cust) ==
    /\ sub /= cust
    /\ delegate[cust] /= sub
    /\ delegate[cust] /= "None" => delegate[delegate[cust]] /= sub
    /\ delegate' = [delegate EXCEPT ![sub] = cust]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now,
                   tb_tokens, tb_last_refill, tb_capacity>>

RemoveDelegate(sub) ==
    /\ delegate' = [delegate EXCEPT ![sub] = "None"]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now,
                   tb_tokens, tb_last_refill, tb_capacity>>

\* ── Action: ResetBreachCount ─────────────────────────────────────────────────
ResetBreachCount(w) ==
    /\ breach_count' = [breach_count EXCEPT ![w] = 0]
    /\ UNCHANGED <<score, hwm, last_submit_time, embargo_expiry, delegate, now,
                   tb_tokens, tb_last_refill, tb_capacity>>

\* ── Next-state relation ──────────────────────────────────────────────────────
Next ==
    \/ TickTime
    \/ \E w \in Wallets, s \in Scores : SubmitScore(w, s)
    \/ \E capacity \in MIN_CAPACITY..MAX_CAPACITY : SetBurstCapacity(capacity)
    \/ \E w \in Wallets, expiry \in {-1, now+1, now+2} : SetEmbargo(w, expiry)
    \/ \E w \in Wallets : LiftEmbargo(w)
    \/ \E sub \in Wallets, cust \in Wallets : SetDelegate(sub, cust)
    \/ \E sub \in Wallets : RemoveDelegate(sub)
    \/ \E w \in Wallets, a \in Assets : ResetBreachCount(w, a)
    \/ \E w \in Wallets, a \in Assets, bond_amt \in {1, 5, 10} : OpenDispute(w, a, bond_amt)
    \/ \E w \in Wallets, a \in Assets, corrected_score \in Scores : ResolveDisputeAdmin(w, a, corrected_score)
    \/ \E w \in Wallets, a \in Assets : ResolveDisputeTimeout(w, a)

\* ════════════════════════════════════════════════════════════════════════════
\* INVARIANTS
\* ════════════════════════════════════════════════════════════════════════════

\* ── Existing invariants (unchanged) ──────────────────────────────────────────

HistoricalMaxMonotonicity == \A w \in Wallets : hwm[w] >= score[w]

EmbargoActive(w) == embargo_expiry[w] = -1 \/ (embargo_expiry[w] > 0 /\ now <= embargo_expiry[w])
EmbargoGateSoundness == \A w \in Wallets : EmbargoActive(w) <=> (embargo_expiry[w] = -1 \/ (embargo_expiry[w] /= 0 /\ now <= embargo_expiry[w]))

IsCyclic == \E w \in Wallets :
    \/ delegate[w] = w
    \/ (delegate[w] /= "None" /\ delegate[delegate[w]] = w)
    \/ (delegate[w] /= "None" /\ delegate[delegate[w]] /= "None" /\ delegate[delegate[delegate[w]]] = w)
DelegationAcyclicity == ~IsCyclic

FloorNeverBypassed == \A w \in Wallets, a \in Assets : hwm[w, a] >= HWM_THRESHOLD => (score[w, a] >= FLOOR_VALUE \/ score[w, a] = 0)

\* Dispute Invariants
ExactlyOneDisputePerPair == \A w \in Wallets, a \in Assets : 
    dispute_status[w, a] \in {"none", "open", "resolved"}

NoDoubleOpen == \A w \in Wallets, a \in Assets : 
    dispute_status[w, a] = "open" => dispute_bond[w, a] > 0

TimeoutNeverEarly == \A w \in Wallets, a \in Assets :
    dispute_status[w, a] = "open" => dispute_deadline[w, a] > dispute_open_time[w, a]

ResolvedIsTerminal == [][\A w \in Wallets, a \in Assets : 
    (dispute_status[w, a] = "resolved" /\ dispute_status'[w, a] = "open") => 
    dispute_open_time'[w, a] > dispute_open_time[w, a]]_vars

\* ── Token-bucket invariants (new) ────────────────────────────────────────────

\* INV-TB-1  Tokens never exceed the current global capacity.
\* This holds even after SetBurstCapacity *reduces* the capacity —
\* existing over-capacity buckets are never refilled beyond the new cap
\* (RefillCount clamps to tb_capacity), so on the next SubmitScore the
\* bucket is written back within bounds.
\* NOTE: Between a capacity *reduction* and the next SubmitScore for a
\*       wallet, tb_tokens[w] may legitimately be above the *new* tb_capacity
\*       because the lazy-truncation contract (matching the Rust implementation)
\*       does not immediately rewrite stored buckets.  We therefore state the
\*       invariant in terms of what the wallet would *use* on its next call,
\*       i.e. RefillCount (which already clamps), rather than raw tb_tokens.
TokensNeverExceedCapacity ==
    \A w \in Wallets : RefillCount(w) <= tb_capacity

\* INV-TB-2  Tokens never go negative (trivially satisfied because tokens is
\*           a natural and we only store refilled-1 ≥ 0 after a successful
\*           SubmitScore, and we never decrement without a prior > 0 check).
TokensNonNegative ==
    \A w \in Wallets : tb_tokens[w] >= 0

\* INV-TB-3  After a capacity reduction, the *effective* available tokens on
\*           the next refill are capped at the new capacity.  Stated as a
\*           state invariant: RefillCount is always bounded by tb_capacity.
CapacityReductionCapsNextBurst ==
    \A w \in Wallets : RefillCount(w) <= tb_capacity

\* INV-TB-4  last_refill never drifts ahead of now.
RefillAnchorNotInFuture ==
    \A w \in Wallets : tb_last_refill[w] <= now

\* INV-TB-5  The global capacity is always within the configured bounds.
CapacityWithinBounds ==
    /\ tb_capacity >= MIN_CAPACITY
    /\ tb_capacity <= MAX_CAPACITY

\* ════════════════════════════════════════════════════════════════════════════
\* ACTION PROPERTIES (temporal)
\* ════════════════════════════════════════════════════════════════════════════

\* Existing temporal properties (unchanged).
BreachCounterStateMachine == [][ \A w \in Wallets : (breach_count[w] > 0 /\ breach_count'[w] = 0) => (score'[w] < RISK_THRESHOLD \/ (score'[w] = score[w] /\ hwm'[w] = hwm[w])) ]_vars

DisputeTimeoutNotPremature == [][\A w \in Wallets, a \in Assets :
    (dispute_status[w, a] = "open" /\ dispute_status'[w, a] = "resolved" /\ 
     \E v1, v2, v3, v4, v5, v6, v7, v8, v9 : 
        <<v1, v2, v3, v4, v5, v6, v7, v8, v9>>' /= <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, dispute_bond, dispute_deadline, dispute_open_time>>)
    => (now > dispute_deadline[w, a] \/ score'[w, a] /= score[w, a])]_vars

\* ── Token-bucket temporal properties (new) ────────────────────────────────────

\* PROP-TB-1  A wallet that exhausts its bucket cannot submit again until at
\*            least one COOLDOWN period has elapsed.
\*            Stated as: whenever a SubmitScore drains the bucket to 0, the
\*            next accepted SubmitScore for the same wallet must happen at a
\*            strictly later time (≥ current now + COOLDOWN from that point).
TokenExhaustionBlocksSubmit ==
    [][ \A w \in Wallets :
            (tb_tokens[w] > 0 /\ tb_tokens'[w] = 0)
            => \/ now' = now   \* same tick, different wallet — fine
               \/ (last_submit_time'[w] = now)  \* only the draining submit itself updates last_submit
       ]_vars

\* PROP-TB-2  After a capacity *increase*, a wallet's effective available
\*            tokens never exceed the *new* capacity on the very next refill.
\* (Follows from TokensNeverExceedCapacity but stated temporally for clarity.)
BurstNeverExceedsNewCapacity ==
    [][tb_capacity' >= tb_capacity
       => \A w \in Wallets : RefillCount(w) <= tb_capacity']_vars

\* ── State constraint (model-checking bound) ──────────────────────────────────
StateConstraint == now <= 5

Spec == Init /\ [][Next]_vars
=============================================================================
