#[cfg(test)]
mod test_event_schema {
    use soroban_sdk::{
        testutils::{Address as _, Events as _},
        Address, Env, IntoVal, Vec,
    };

    use crate::{events::EVENT_VERSION, LedgerLensScoreContract, LedgerLensScoreContractClient};

    #[test]
    fn test_all_events_carry_schema_version() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, LedgerLensScoreContract);
        let client = LedgerLensScoreContractClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let service = Address::generate(&env);

        // This triggers a subset of events (initialization, watch, etc.)
        client.initialize(&admin, &service);
        let wallet = Address::generate(&env);
        client.set_watchlist(&Vec::new(&env), &wallet, &true);

        let all_events = env.events().all();
        
        // Assert every single event emitted by this contract has EVENT_VERSION as its second topic.
        for (addr, topics, _data) in all_events.iter() {
            if addr == contract_id {
                assert!(
                    topics.len() >= 2,
                    "event topic array too short to contain schema version"
                );
                // First topic is event name, second is schema version
                let version_topic: u32 = topics.get(1).unwrap().into_val(&env);
                assert_eq!(
                    version_topic, EVENT_VERSION,
                    "event missing correct schema version in topics"
                );
            }
        }
    }
}
