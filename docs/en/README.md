# MultiChSync Documentation (English)

Welcome to the MultiChSync English documentation. This directory contains:

- `architecture/`: Architecture decisions and principles
- `guides/`: Usage guides and tutorials
- `api/`: API reference documentation
- `technical/`: Technical specifications
- `contributing/`: Development guidelines

## Quick Links

### Guides
- [Installation Guide](guides/installation.md) - Setup and requirements
- [Quickstart Guide](guides/quickstart.md) - End-to-end workflow
- [fNIRS Conversion Guide](guides/fnirs_conversion.md) - Shimadzu to SNIRF conversion
- [EEG Conversion Guide](guides/eeg_conversion.md) - Curry/EEGLAB to BrainVision conversion
- [ECG Conversion Guide](guides/ecg_conversion.md) - Biopac ACQ to CSV conversion
- [Marker Processing Guide](guides/marker_processing.md) - Multi-device marker synchronization
- [Quality Assessment Guide](guides/quality_assessment.md) - fNIRS signal quality evaluation

### Reference
- [API Reference](api/index.md) - Python interface documentation
- [Architecture Overview](architecture/overview.md) - System design
- [Technical Specifications](technical/) - Detailed technical docs

### Development
- [Agent Guidelines](contributing/agents.md) - Development workflow for AI agents
- [Code Style Guide](contributing/CODE_STYLE.md) - Coding conventions and patterns

## Documentation Structure

```
docs/en/
├── architecture/           # Architecture decisions and principles
│   └── overview.md        # System architecture overview
├── guides/                # Usage guides and tutorials
│   ├── installation.md    # Installation guide
│   ├── quickstart.md      # Quickstart guide
│   ├── fnirs_conversion.md # fNIRS conversion guide
│   ├── eeg_conversion.md  # EEG conversion guide
│   ├── ecg_conversion.md  # ECG conversion guide
│   ├── marker_processing.md # Marker processing guide
│   └── quality_assessment.md # Quality assessment guide
├── api/                   # API reference documentation
│   └── index.md          # API reference index
├── technical/             # Technical specifications
│   ├── fnirs_signal_level_qc_metrics.md # fNIRS quality metrics spec
│   └── event_matching_analysis.md      # Event matching analysis spec
└── contributing/          # Development guidelines
    ├── agents.md         # Agent development workflow
    └── CODE_STYLE.md     # Code style guide (mixed English/Chinese)
```

## Getting Help

If you need help with MultiChSync:

1. Check the [guides](guides/) for step-by-step instructions
2. Review the [API reference](api/index.md) for Python usage
3. Examine the [technical specifications](technical/) for detailed algorithms
4. Refer to the [architecture overview](architecture/overview.md) for system design

## Contributing to English Documentation

We welcome contributions to improve the English documentation. Please follow the [Code Style Guide](contributing/CODE_STYLE.md) for writing conventions.

When updating documentation:

1. Ensure all examples are runnable and up-to-date
2. Update both guides and API references when behavior changes
3. Keep language clear and concise
4. Use consistent terminology across all documents

## Related Documentation

- [Chinese Documentation](../zh/README.md) - 中文文档
- [Project README](../../README.md) - Main project overview