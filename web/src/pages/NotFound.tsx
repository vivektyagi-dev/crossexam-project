import { FileQuestion, Home } from "lucide-react";
import { Card, EmptyState, LinkButton } from "../components/ui";

export function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={FileQuestion}
        title="This page is not in the file"
        action={
          <LinkButton to="/" icon={Home}>
            Back to the overview
          </LinkButton>
        }
      >
        The link may be old, or the pack may have been removed.
      </EmptyState>
    </Card>
  );
}
