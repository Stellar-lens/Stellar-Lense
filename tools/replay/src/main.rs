mod schema;

use anyhow::{Context, Result};
use serde::Deserialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};

use soroban_sdk::testutils::Address as _;
use soroban_sdk::{Address, Env, Symbol, Vec as SVec};

use ledgerlens_score::{LedgerLensScoreContract, LedgerLensScoreContractClient, ScoreSubmission};
use schema::{ReplayEntryV1, ReplayFileHeader, ReplayMetadata};

#[derive(Debug, Deserialize)]
struct SnapshotEntry {
    wallet: String,
    asset_pair: String,
    trades: Option<Vec<serde_json::Value>>,
}

fn parse_price_average(trades: &Option<Vec<serde_json::Value>>) -> Option<f64> {
    trades.as_ref().and_then(|t| {
        let mut sum = 0.0f64;
        let mut cnt = 0usize;
        for v in t.iter() {
            if let Some(p) = v.get("price").and_then(|p| p.as_f64()) {
                sum += p;
                cnt += 1;
            }
        }
        if cnt == 0 {
            None
        } else {
            Some(sum / cnt as f64)
        }
    })
}

fn process_snapshot(
    path: &str,
    env: &Env,
    client: &LedgerLensScoreContractClient,
) -> Result<usize> {
    let f = File::open(path).context("opening snapshot file")?;
    let reader = BufReader::new(f);
    let mut count = 0usize;
    let mut addr_map: HashMap<String, Address> = HashMap::new();
    let mut schema_version: Option<u32> = None;

    for line in reader.lines() {
        let l = line?;
        if l.trim().is_empty() {
            continue;
        }

        // Try to parse as header on first line
        if count == 0 {
            if let Ok(header) = serde_json::from_str::<ReplayFileHeader>(&l) {
                // This is a schema header line
                schema::validate_schema_version(header.schema_version)
                    .map_err(|e| anyhow::anyhow!("Schema validation failed: {}", e))?;
                schema_version = Some(header.schema_version);
                println!(
                    "Loaded replay with schema version {} (supported: {})",
                    header.schema_version,
                    schema::supported_versions()
                        .iter()
                        .map(|v| v.to_string())
                        .collect::<Vec<_>>()
                        .join(", ")
                );
                if let Some(ref metadata) = header.metadata {
                    if let Some(ref desc) = metadata.description {
                        println!("Description: {}", desc);
                    }
                    if let Some(ref host_ver) = metadata.host_version {
                        println!("Host version: {}", host_ver);
                    }
                }
                continue;
            }
        }

        // Parse entry with backward compatibility
        let entry: SnapshotEntry = serde_json::from_str(&l).context("parsing ndjson line")?;
        let wallet_addr =
            addr_map.entry(entry.wallet.clone()).or_insert_with(|| Address::generate(env)).clone();
        let pair_sym = Symbol::new(env, &entry.asset_pair);

        // derive a simple heuristic score from average price
        let score = parse_price_average(&entry.trades)
            .map(|avg| {
                let s = (avg * 10.0).round() as i64;
                s.clamp(0, 100) as u32
            })
            .unwrap_or(50u32);

        let mut batch: SVec<ScoreSubmission> = SVec::new(env);
        batch.push_back(ScoreSubmission {
            wallet: wallet_addr.clone(),
            asset_pair: pair_sym.clone(),
            score,
            benford_flag: false,
            ml_flag: false,
            timestamp: 1u64,
            confidence: 80u32,
            model_version: 1u32,
        });

        let result = client.submit_scores_batch(&batch);
        println!(
            "submitted wallet={}, pair={} -> accepted_count={} rejected_count={}",
            entry.wallet, entry.asset_pair, result.accepted_count, result.rejected_count
        );
        count += 1;
    }

    if let Some(ver) = schema_version {
        println!("Processed {} entries with schema version {}", count, ver);
    } else {
        println!("Processed {} entries (no explicit schema version found - using implicit v1)", count);
    }

    Ok(count)
}

fn main() -> Result<()> {
    let path = "testdata/reference.ndjson";
    println!("Replay — reading {}", path);

    let env = Env::default();
    env.mock_all_auths();
    let contract_id = env.register_contract(None, LedgerLensScoreContract);
    let client = LedgerLensScoreContractClient::new(&env, &contract_id);
    let admin = Address::generate(&env);
    let service = Address::generate(&env);
    client.initialize(&admin, &service);

    match process_snapshot(path, &env, &client) {
        Ok(n) => println!("processed {} entries", n),
        Err(e) => println!("error processing snapshot: {:#}", e),
    }
    Ok(())
}
