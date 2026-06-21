import { ResolvenApp } from "../../resolven-app";

export default async function EventPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  const { eventId } = await params;
  return <ResolvenApp initialRoute="event" initialEventId={Number(eventId)} />;
}
