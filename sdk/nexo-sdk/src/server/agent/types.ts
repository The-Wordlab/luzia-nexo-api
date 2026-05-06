/**
 * Agent tool interface.
 *
 * Works in both modes:
 * - Self-hosted: app calls execute() locally in its agent loop
 * - Nexo-managed: Nexo calls the tool via the app's webhook
 */

export interface AgentTool {
  name: string;
  description: string;
  inputSchema: string;
  execute(args: Record<string, unknown>): Promise<unknown>;
}
