# Ada Documentation

Comprehensive guides and documentation for the Ada Autonomous AI Software Engineering system.

## 📚 Documentation Index

### Getting Started

- **[Main README](../README.md)** - Project overview, quick start, and basic configuration
- **[Webhook Setup Guide](WEBHOOK_SETUP.md)** - Configure GitHub/GitLab webhooks for automation

### Architecture & Design

- **[Design Document](../design_doc/design.md)** - System architecture and design decisions

### Operation Guides

- **[Worker Setup](../README_WORKER.md)** - Configure and scale background workers
- **[Isolation Backends](../ISOLATION.md)** - Understanding sandbox, Docker, and ECS execution environments

## 🔗 Quick Links by Use Case

### I want to...

**Set up Ada for the first time**
1. Read [Main README](../README.md) - Installation and configuration
2. Configure webhooks: [Webhook Setup Guide](WEBHOOK_SETUP.md)
3. Deploy workers: [Worker Setup](../README_WORKER.md)

**Integrate with my VCS platform**
- [Webhook Setup Guide](WEBHOOK_SETUP.md) - GitHub and GitLab integration

**Scale Ada for production**
- [Worker Setup](../README_WORKER.md) - Horizontal scaling and concurrency
- [Isolation Backends](../ISOLATION.md) - Choose between sandbox/Docker/ECS

**Understand how Ada works**
- [Design Document](../design_doc/design.md) - Architecture deep dive
- [Main README](../README.md#architecture) - System flow diagrams

**Troubleshoot issues**
- [Webhook Setup Guide](WEBHOOK_SETUP.md#troubleshooting) - Webhook debugging
- Check application logs: `docker-compose logs -f api worker`

## 📖 Additional Resources

### Configuration Examples

See example configuration files:
- [env.example](../env.example) - All available environment variables
- [example_story.json](../example_files/example_story.json) - User story format
- [epic_backlog.json](../example_files/epic_backlog.json) - Multi-story backlog format

### Code Structure

```
ada-coding-agent/
├── docs/                    # 📖 You are here
│   ├── README.md           # This documentation index
│   └── WEBHOOK_SETUP.md    # VCS webhook configuration guide
├── design_doc/             # Architecture documentation
├── api/                    # FastAPI backend
├── agents/                 # AI agent implementations
├── orchestrator/           # Story execution pipeline
├── tools/                  # VCS clients and utilities
├── worker/                 # Celery background tasks
├── isolation/              # Execution environments
└── ui/                     # Next.js console interface
```

## 🆘 Getting Help

1. **Check the docs** - Start with the relevant guide above
2. **Review logs** - Most issues show errors in application logs
3. **Verify configuration** - Compare your `.env` with [env.example](../env.example)
4. **Test components** - Run `python test_components.py` to verify setup

## 🤝 Contributing to Documentation

When adding new features or making significant changes:

1. Update relevant documentation files
2. Add entries to this index if creating new docs
3. Keep examples up-to-date with code changes
4. Include troubleshooting sections for common issues

---

**Last Updated:** March 2026
