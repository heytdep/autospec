# AutoSpec

Formal specification auto-research system. See `program.md` for the full design.

## Skills

- `autospec`: main orchestrator. Invoke with `autospec <spec_path> --properties <props_path> --trust-model <tm_path>`

Skill definition: `skills/autospec/SKILL.md`

## Agents

All agent definitions are in `agents/`. The orchestrator launches them as needed:

| Agent | Role | Model |
|---|---|---|
| autospec-compartmentalizer | splits spec into compartments | sonnet |
| autospec-proposer | proposes structural improvements | opus |
| autospec-reviewer | adversarial review of proposals | opus |
| autospec-judge | rules on proposer/reviewer disputes | sonnet |
| autospec-seeder | initializes techniques registry | sonnet |
| autospec-checkpoint | writes checkpoint summaries | sonnet |
| autospec-novelty | prior work search (stage 1) | sonnet |
| autospec-novelty-deep | generality + verification (stages 2-3) | opus |
| autospec-writer | mechanical file I/O for dashboard | sonnet |

## Dashboard

```
python3 dashboard/serve.py
```

Serves at `http://127.0.0.1:8420`. Polls run data every 3 seconds.

## Running

From this directory, invoke the autospec skill with a formal spec. Example:

```
autospec examples/simple_consensus.tla --properties examples/simple_consensus_props.json --trust-model examples/simple_consensus_trust.md
```
