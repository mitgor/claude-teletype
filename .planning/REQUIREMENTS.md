# Requirements: Claude Teletype

**Defined:** 2026-02-20
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.3 Requirements

Requirements for tech debt cleanup. Each maps to roadmap phases.

### Profile Discoverability

- [ ] **PROF-01**: User can reference IBM PPDS printer profile as "ibm" (alias resolving to existing "ppds" profile)

### Config Transparency

- [ ] **CONF-01**: `config show` displays effective merged configuration from all three layers (file, env, CLI flags) with source annotations indicating where each value originates

### User Warnings

- [ ] **WARN-01**: User sees a startup warning when system_prompt is configured but backend is claude-cli (which ignores system_prompt in favor of CLAUDE.md)
- [ ] **WARN-02**: User sees a warning in settings modal when switching away from claude-cli backend that session context will be lost

## Future Requirements

None — this is a cleanup milestone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Renaming "ppds" key to "ibm" | Backward compatibility — existing configs reference "ppds" |
| Full config editing in TUI | Settings modal already handles runtime changes; `config show` is read-only |
| Blocking backend hot-swap | Warning is sufficient; users should be able to swap if they accept the trade-off |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROF-01 | Phase 16 | Pending |
| CONF-01 | Phase 16 | Pending |
| WARN-01 | Phase 17 | Pending |
| WARN-02 | Phase 17 | Pending |

**Coverage:**
- v1.3 requirements: 4 total
- Mapped to phases: 4
- Unmapped: 0

---
*Requirements defined: 2026-02-20*
*Last updated: 2026-02-20 after roadmap creation*
