import { ResolvenApp } from "../../../resolven-app";

export default async function AdminRunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <ResolvenApp initialRoute="admin-run" initialRunId={Number(runId)} />;
}
