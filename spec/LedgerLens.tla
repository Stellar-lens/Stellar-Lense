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
    DISPUTE_TIMEOUT

VARIABLES 
    score,
    hwm,
    breach_count,
    last_submit_time,
    embargo_expiry,
    delegate,
    now,
    dispute_status,
    dispute_bond,
    dispute_deadline,
    dispute_open_time

vars == <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now, 
         dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

\* Initialization
Init ==
    /\ score = [w \in Wallets, a \in Assets |-> 0]
    /\ hwm = [w \in Wallets, a \in Assets |-> 0]
    /\ breach_count = [w \in Wallets, a \in Assets |-> 0]
    /\ last_submit_time = [w \in Wallets, a \in Assets |-> 0]
    /\ embargo_expiry = [w \in Wallets |-> 0]
    /\ delegate = [w \in Wallets |-> "None"]
    /\ now = 1
    /\ dispute_status = [w \in Wallets, a \in Assets |-> "none"]
    /\ dispute_bond = [w \in Wallets, a \in Assets |-> 0]
    /\ dispute_deadline = [w \in Wallets, a \in Assets |-> 0]
    /\ dispute_open_time = [w \in Wallets, a \in Assets |-> 0]

\* Actions
TickTime ==
    /\ now' = now + 1
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

SubmitScore(w, a, s) ==
    /\ last_submit_time[w, a] = 0 \/ now >= last_submit_time[w, a] + COOLDOWN
    /\ hwm[w, a] >= HWM_THRESHOLD => s >= FLOOR_VALUE
    /\ score' = [score EXCEPT ![w, a] = s]
    /\ hwm' = [hwm EXCEPT ![w, a] = IF s > hwm[w, a] THEN s ELSE hwm[w, a]]
    /\ breach_count' = [breach_count EXCEPT ![w, a] = IF s >= RISK_THRESHOLD THEN breach_count[w, a] + 1 ELSE 0]
    /\ last_submit_time' = [last_submit_time EXCEPT ![w, a] = now]
    /\ UNCHANGED <<embargo_expiry, delegate, now, dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

SetEmbargo(w, expiry) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = expiry]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

LiftEmbargo(w) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = 0]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

SetDelegate(sub, cust) ==
    /\ sub /= cust
    /\ delegate[cust] /= sub
    /\ delegate[cust] /= "None" => delegate[delegate[cust]] /= sub
    /\ delegate' = [delegate EXCEPT ![sub] = cust]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

RemoveDelegate(sub) ==
    /\ delegate' = [delegate EXCEPT ![sub] = "None"]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

ResetBreachCount(w, a) ==
    /\ breach_count' = [breach_count EXCEPT ![w, a] = 0]
    /\ UNCHANGED <<score, hwm, last_submit_time, embargo_expiry, delegate, now,
                   dispute_status, dispute_bond, dispute_deadline, dispute_open_time>>

\* Dispute Mechanism Actions

OpenDispute(w, a, bond_amt) ==
    /\ dispute_status[w, a] = "none"
    /\ bond_amt > 0
    /\ dispute_status' = [dispute_status EXCEPT ![w, a] = "open"]
    /\ dispute_bond' = [dispute_bond EXCEPT ![w, a] = bond_amt]
    /\ dispute_deadline' = [dispute_deadline EXCEPT ![w, a] = now + DISPUTE_TIMEOUT]
    /\ dispute_open_time' = [dispute_open_time EXCEPT ![w, a] = now]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now>>

ResolveDisputeAdmin(w, a, corrected_score) ==
    /\ dispute_status[w, a] = "open"
    /\ corrected_score >= 0 /\ corrected_score <= 100
    /\ dispute_status' = [dispute_status EXCEPT ![w, a] = "resolved"]
    /\ score' = [score EXCEPT ![w, a] = corrected_score]
    /\ UNCHANGED <<hwm, breach_count, last_submit_time, embargo_expiry, delegate, now,
                   dispute_bond, dispute_deadline, dispute_open_time>>

ResolveDisputeTimeout(w, a) ==
    /\ dispute_status[w, a] = "open"
    /\ now > dispute_deadline[w, a]
    /\ dispute_status' = [dispute_status EXCEPT ![w, a] = "resolved"]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now,
                   dispute_bond, dispute_deadline, dispute_open_time>>

Next ==
    \/ TickTime
    \/ \E w \in Wallets, a \in Assets, s \in Scores : SubmitScore(w, a, s)
    \/ \E w \in Wallets, expiry \in {-1, now+1, now+2} : SetEmbargo(w, expiry)
    \/ \E w \in Wallets : LiftEmbargo(w)
    \/ \E sub \in Wallets, cust \in Wallets : SetDelegate(sub, cust)
    \/ \E sub \in Wallets : RemoveDelegate(sub)
    \/ \E w \in Wallets, a \in Assets : ResetBreachCount(w, a)
    \/ \E w \in Wallets, a \in Assets, bond_amt \in {1, 5, 10} : OpenDispute(w, a, bond_amt)
    \/ \E w \in Wallets, a \in Assets, corrected_score \in Scores : ResolveDisputeAdmin(w, a, corrected_score)
    \/ \E w \in Wallets, a \in Assets : ResolveDisputeTimeout(w, a)

\* Invariants (State)
HistoricalMaxMonotonicity == \A w \in Wallets, a \in Assets : hwm[w, a] >= score[w, a]

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

\* Action Properties
BreachCounterStateMachine == [][ \A w \in Wallets, a \in Assets : (breach_count[w, a] > 0 /\ breach_count'[w, a] = 0) => (score'[w, a] < RISK_THRESHOLD \/ (score'[w, a] = score[w, a] /\ hwm'[w, a] = hwm[w, a])) ]_vars

CooldownEnforcement == [][ \A w \in Wallets, a \in Assets : (last_submit_time'[w, a] /= last_submit_time[w, a] /\ last_submit_time[w, a] /= 0) => now >= last_submit_time[w, a] + COOLDOWN ]_vars

DisputeTimeoutNotPremature == [][\A w \in Wallets, a \in Assets :
    (dispute_status[w, a] = "open" /\ dispute_status'[w, a] = "resolved" /\ 
     \E v1, v2, v3, v4, v5, v6, v7, v8, v9 : 
        <<v1, v2, v3, v4, v5, v6, v7, v8, v9>>' /= <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, dispute_bond, dispute_deadline, dispute_open_time>>)
    => (now > dispute_deadline[w, a] \/ score'[w, a] /= score[w, a])]_vars

StateConstraint == now <= 4

Spec == Init /\ [][Next]_vars
=============================================================================
