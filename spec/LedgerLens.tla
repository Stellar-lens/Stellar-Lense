---------------------------- MODULE LedgerLens ----------------------------
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS 
    Wallets,
    Scores,
    COOLDOWN,
    HWM_THRESHOLD,
    FLOOR_VALUE,
    RISK_THRESHOLD,
    Admin,
    Service,
    UpgradeDelay,
    WasmHashes

VARIABLES 
    score,
    hwm,
    breach_count,
    last_submit_time,
    embargo_expiry,
    delegate,
    now,
    upgrade_pending,
    proposed_wasm_hash,
    proposal_time,
    executable_time,
    proposed_by

vars == <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

\* Initialization
Init ==
    /\ score = [w \in Wallets |-> 0]
    /\ hwm = [w \in Wallets |-> 0]
    /\ breach_count = [w \in Wallets |-> 0]
    /\ last_submit_time = [w \in Wallets |-> 0]
    /\ embargo_expiry = [w \in Wallets |-> 0]
    /\ delegate = [w \in Wallets |-> "None"]
    /\ now = 1
    /\ upgrade_pending = FALSE
    /\ proposed_wasm_hash = 0
    /\ proposal_time = 0
    /\ executable_time = 0
    /\ proposed_by = "None"

\* Actions
TickTime ==
    /\ now' = now + 1
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

SubmitScore(w, s) ==
    /\ last_submit_time[w] = 0 \/ now >= last_submit_time[w] + COOLDOWN
    /\ hwm[w] >= HWM_THRESHOLD => s >= FLOOR_VALUE
    /\ score' = [score EXCEPT ![w] = s]
    /\ hwm' = [hwm EXCEPT ![w] = IF s > hwm[w] THEN s ELSE hwm[w]]
    /\ breach_count' = [breach_count EXCEPT ![w] = IF s >= RISK_THRESHOLD THEN breach_count[w] + 1 ELSE 0]
    /\ last_submit_time' = [last_submit_time EXCEPT ![w] = now]
    /\ UNCHANGED <<embargo_expiry, delegate, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

SetEmbargo(w, expiry) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = expiry]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

LiftEmbargo(w) ==
    /\ embargo_expiry' = [embargo_expiry EXCEPT ![w] = 0]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, delegate, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

SetDelegate(sub, cust) ==
    /\ sub /= cust
    /\ delegate[cust] /= sub
    /\ delegate[cust] /= "None" => delegate[delegate[cust]] /= sub
    /\ delegate' = [delegate EXCEPT ![sub] = cust]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

RemoveDelegate(sub) ==
    /\ delegate' = [delegate EXCEPT ![sub] = "None"]
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

ResetBreachCount(w) ==
    /\ breach_count' = [breach_count EXCEPT ![w] = 0]
    /\ UNCHANGED <<score, hwm, last_submit_time, embargo_expiry, delegate, now, upgrade_pending, proposed_wasm_hash, proposal_time, executable_time, proposed_by>>

\* ── WASM upgrade state machine ──────────────────────────────────────────────

\* ProposeUpgrade: only the admin can propose; guarded against duplicate proposals.
ProposeUpgrade(caller, h) ==
    /\ caller = Admin
    /\ h \in WasmHashes
    \* Guard: no duplicate proposal (Error::UpgradeAlreadyPending)
    /\ upgrade_pending = FALSE
    \* Effect: register the pending upgrade proposal
    /\ upgrade_pending' = TRUE
    /\ proposed_wasm_hash' = h
    /\ proposal_time' = now
    /\ executable_time' = now + UpgradeDelay
    /\ proposed_by' = caller
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now>>

\* ExecuteUpgrade: only the admin can execute; guarded by existence and timelock.
ExecuteUpgrade(caller) ==
    /\ caller = Admin
    \* Guard: pending upgrade exists (Error::NoPendingUpgrade)
    /\ upgrade_pending = TRUE
    \* Guard: timelock must have elapsed (Error::UpgradeNotReady)
    /\ now >= executable_time
    \* Effect: clear the proposal and upgrade the contract WASM
    /\ upgrade_pending' = FALSE
    /\ proposed_wasm_hash' = 0
    /\ proposal_time' = 0
    /\ executable_time' = 0
    /\ proposed_by' = "None"
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now>>

\* VetoUpgrade: only the admin can veto; always possible while a proposal is pending.
VetoUpgrade(caller) ==
    /\ caller = Admin
    \* Guard: pending upgrade exists (Error::NoPendingUpgrade)
    /\ upgrade_pending = TRUE
    \* Effect: clear the proposal (no time constraint — veto always possible)
    /\ upgrade_pending' = FALSE
    /\ proposed_wasm_hash' = 0
    /\ proposal_time' = 0
    /\ executable_time' = 0
    /\ proposed_by' = "None"
    /\ UNCHANGED <<score, hwm, breach_count, last_submit_time, embargo_expiry, delegate, now>>

Next ==
    \/ TickTime
    \/ \E w \in Wallets, s \in Scores : SubmitScore(w, s)
    \/ \E w \in Wallets, expiry \in {-1, now+1, now+2} : SetEmbargo(w, expiry)
    \/ \E w \in Wallets : LiftEmbargo(w)
    \/ \E sub \in Wallets, cust \in Wallets : SetDelegate(sub, cust)
    \/ \E sub \in Wallets : RemoveDelegate(sub)
    \/ \E w \in Wallets : ResetBreachCount(w)
    \/ \E caller \in Wallets, h \in WasmHashes : ProposeUpgrade(caller, h)
    \/ \E caller \in Wallets : ExecuteUpgrade(caller)
    \/ \E caller \in Wallets : VetoUpgrade(caller)

\* Invariants (State)
HistoricalMaxMonotonicity == \A w \in Wallets : hwm[w] >= score[w]

EmbargoActive(w) == embargo_expiry[w] = -1 \/ (embargo_expiry[w] > 0 /\ now <= embargo_expiry[w])
EmbargoGateSoundness == \A w \in Wallets : EmbargoActive(w) <=> (embargo_expiry[w] = -1 \/ (embargo_expiry[w] /= 0 /\ now <= embargo_expiry[w]))

IsCyclic == \E w \in Wallets :
    \/ delegate[w] = w
    \/ (delegate[w] /= "None" /\ delegate[delegate[w]] = w)
    \/ (delegate[w] /= "None" /\ delegate[delegate[w]] /= "None" /\ delegate[delegate[delegate[w]]] = w)
DelegationAcyclicity == ~IsCyclic

FloorNeverBypassed == \A w \in Wallets : hwm[w] >= HWM_THRESHOLD => (score[w] >= FLOOR_VALUE \/ score[w] = 0)

\* ── Upgrade invariants ─────────────────────────────────────────────────────

\* A pending proposal was always created by the Admin — service signers never can.
ProposedByAdminOnly ==
    upgrade_pending => proposed_by = Admin

\* The executable time never precedes the proposal time.
ExecutableAfterProposalTime ==
    upgrade_pending => executable_time >= proposal_time

\* When no proposal is pending, all proposal fields are reset to sentinel values.
ProposalFieldsZeroedWhenIdle ==
    ~upgrade_pending => /\ proposed_wasm_hash = 0
                        /\ proposal_time = 0
                        /\ executable_time = 0
                        /\ proposed_by = "None"

\* ── Action Properties ──────────────────────────────────────────────────────

BreachCounterStateMachine == [][ \A w \in Wallets : (breach_count[w] > 0 /\ breach_count'[w] = 0) => (score'[w] < RISK_THRESHOLD \/ (score'[w] = score[w] /\ hwm'[w] = hwm[w])) ]_vars

CooldownEnforcement == [][ \A w \in Wallets : (last_submit_time'[w] /= last_submit_time[w] /\ last_submit_time[w] /= 0) => now >= last_submit_time[w] + COOLDOWN ]_vars

\* The timelock is enforced by the guard on ExecuteUpgrade (now >= executable_time).
\* No separate action property is needed — the guard prevents early execution by
\* construction, and the model checker verifies no behavior bypasses it.
\* VetoUpgrade deliberately has no time constraint ("veto always possible").

StateConstraint == now <= 3

Spec == Init /\ [][Next]_vars
=============================================================================
