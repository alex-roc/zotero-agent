// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// GitHub Pages for repo alex-roc/zotero-agent -> served under /zotero-agent.
export default defineConfig({
  site: 'https://alex-roc.github.io',
  base: '/zotero-agent',
  integrations: [
    starlight({
      title: 'zotero-agent',
      description:
        'Full local control of your Zotero library — from your terminal or your AI agent. No cloud, no API key.',
      tagline:
        'Full local control of your Zotero library — from your terminal or your AI agent. No cloud, no API key.',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/alex-roc/zotero-agent',
        },
      ],
      // Pagefind is Starlight's built-in, self-hosted search (CSP-safe, no external service).
      pagefind: true,
      editLink: {
        baseUrl:
          'https://github.com/alex-roc/zotero-agent/edit/main/web/',
      },
      sidebar: [
        {
          label: 'Getting started',
          items: [
            { label: 'Install', link: '/getting-started/install/' },
            { label: 'Quickstart: CLI', link: '/getting-started/quickstart-cli/' },
            { label: 'Quickstart: AI agent', link: '/getting-started/quickstart-agent/' },
          ],
        },
        {
          label: 'Cookbook',
          items: [
            { label: 'Overview', link: '/cookbook/' },
            { label: 'Clean 500 items', link: '/cookbook/clean-500-items/' },
            { label: 'Summarize a PDF into a note', link: '/cookbook/summarize-pdf-to-note/' },
            { label: 'Bulk-tag by topic', link: '/cookbook/bulk-tag-by-topic/' },
            { label: 'Dedupe and merge', link: '/cookbook/dedupe-and-merge/' },
            { label: 'Import by identifier', link: '/cookbook/import-by-identifier/' },
            { label: 'Find missing metadata', link: '/cookbook/find-missing-metadata/' },
          ],
        },
        {
          label: 'AI agents',
          items: [
            { label: 'MCP overview', link: '/ai-agents/mcp/' },
            { label: 'Claude Code', link: '/ai-agents/claude-code/' },
            { label: 'Codex CLI', link: '/ai-agents/codex-cli/' },
            { label: 'Gemini CLI', link: '/ai-agents/gemini-cli/' },
            { label: 'Cursor', link: '/ai-agents/cursor/' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Commands', link: '/reference/commands/' },
            { label: 'Configuration', link: '/reference/configuration/' },
            { label: 'zot exec (JS recipes)', link: '/reference/zot-exec-js/' },
          ],
        },
        {
          label: 'Understand',
          items: [
            { label: 'Security model', link: '/security/' },
            { label: 'Architecture', link: '/architecture/' },
            { label: 'Compare', link: '/compare/' },
            { label: 'FAQ', link: '/faq/' },
          ],
        },
      ],
    }),
  ],
});
