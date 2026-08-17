"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Mail, ShieldCheck, UserRound, Users } from "lucide-react";

import { ActionMenu } from "@/app/components/ui/ActionMenu";
import { Badge, RoleBadge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { DataTable } from "@/app/components/ui/DataTable";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { ConfirmDialog } from "@/app/components/ui/Overlay";
import { Metric, MetricStrip, PageHeader } from "@/app/components/ui/PageHeader";
import { Pagination } from "@/app/components/ui/Pagination";
import { SkeletonMetrics, SkeletonTable } from "@/app/components/ui/Skeleton";
import {
  ActiveFilters,
  FilterSelect,
  FilterSheet,
  RefreshButton,
  SearchInput,
  Toolbar,
} from "@/app/components/ui/Toolbar";
import { updateAdminUserRole } from "@/lib/api";
import type { AdminUser } from "@/lib/api";
import { queryKeys, useAdminUserListQuery } from "@/lib/queries";
import { formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

const PAGE_SIZE = 20;

const ROLE_OPTIONS = [
  { value: "all", label: "Role" },
  { value: "admin", label: "Admins" },
  { value: "user", label: "Users" },
];

const NOTIFICATION_OPTIONS = [
  { value: "all", label: "Notifications" },
  { value: "email", label: "Email enabled" },
  { value: "in_app", label: "In-app only" },
];

type Filters = { q: string; role: string; notifications: string };

const EMPTY_FILTERS: Filters = { q: "", role: "all", notifications: "all" };

function displayName(user: AdminUser) {
  return user.full_name?.trim() || user.email || "Unnamed account";
}

/** User management console: identity first, role as a badge, actions in a menu. */
export function AdminUsersView() {
  const { token, userEmail, setStatusMessage } = useWorkspace();
  const queryClient = useQueryClient();

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [pendingRole, setPendingRole] = useState<{
    user: AdminUser;
    role: "user" | "admin";
  } | null>(null);

  const query = useAdminUserListQuery(token, true, {
    ...filters,
    page,
    page_size: PAGE_SIZE,
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "user" | "admin" }) =>
      updateAdminUserRole(userId, role, token),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.users });
      void query.refetch();
      setStatusMessage(
        variables.role === "admin"
          ? "Administrator access granted."
          : "Administrator access revoked.",
      );
      setPendingRole(null);
    },
    onError: (error) => {
      setStatusMessage(
        error instanceof Error ? error.message : "Unable to update user role.",
      );
      setPendingRole(null);
    },
  });

  function updateFilter(changes: Partial<Filters>) {
    setFilters((current) => ({ ...current, ...changes }));
    setPage(1);
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }

  const activeFilters = useMemo(() => {
    const entries: Array<{ key: string; label: string; onRemove: () => void }> = [];
    if (filters.q) {
      entries.push({
        key: "q",
        label: `Search: ${filters.q}`,
        onRemove: () => updateFilter({ q: "" }),
      });
    }
    if (filters.role !== "all") {
      entries.push({
        key: "role",
        label: filters.role === "admin" ? "Admins" : "Users",
        onRemove: () => updateFilter({ role: "all" }),
      });
    }
    if (filters.notifications !== "all") {
      entries.push({
        key: "notifications",
        label:
          filters.notifications === "email" ? "Email enabled" : "In-app only",
        onRemove: () => updateFilter({ notifications: "all" }),
      });
    }
    return entries;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const filterControls = (
    <>
      <FilterSelect
        label="Role"
        value={filters.role}
        options={ROLE_OPTIONS}
        onChange={(value) => updateFilter({ role: value })}
      />
      <FilterSelect
        label="Notifications"
        value={filters.notifications}
        options={NOTIFICATION_OPTIONS}
        onChange={(value) => updateFilter({ notifications: value })}
      />
    </>
  );

  const users = query.data?.items ?? [];
  const summary = query.data?.summary;
  const hasFilters = activeFilters.length > 0;

  return (
    <div className="rv-page">
      <PageHeader
        eyebrow="Operations"
        title="Users"
        description="Manage accounts, administrator access and alert delivery."
        actions={
          <RefreshButton
            onClick={() => void query.refetch()}
            loading={query.isFetching}
            label="Refresh user directory"
          />
        }
      />

      {query.isLoading ? (
        <SkeletonMetrics count={3} />
      ) : summary ? (
        <MetricStrip ariaLabel="User directory summary">
          <Metric label="Total users" value={summary.total} />
          <Metric label="Administrators" value={summary.admins} />
          <Metric label="Email alerts on" value={summary.email_enabled} />
        </MetricStrip>
      ) : null}

      <Toolbar
        ariaLabel="User filters"
        search={
          <SearchInput
            label="Search users"
            placeholder="Search by name or email"
            value={filters.q}
            onChange={(value) => updateFilter({ q: value })}
          />
        }
        filters={
          <>
            <span className="rv-toolbar__desktop-filters">{filterControls}</span>
            <span className="rv-toolbar__mobile-filters">
              <FilterSheet
                title="Filter users"
                activeCount={activeFilters.filter((entry) => entry.key !== "q").length}
                onClear={clearFilters}
              >
                {filterControls}
              </FilterSheet>
            </span>
          </>
        }
      />

      {hasFilters ? (
        <ActiveFilters entries={activeFilters} onClearAll={clearFilters} />
      ) : null}

      {query.isLoading ? (
        <SkeletonTable rows={8} columns={5} label="Loading users" />
      ) : query.isError ? (
        <ErrorState
          title="Unable to load users"
          body="We couldn't retrieve the user directory."
          error={query.error}
          onRetry={() => void query.refetch()}
          showTechnicalDetails
        />
      ) : users.length ? (
        <>
          <DataTable
            caption="User directory"
            rows={users}
            rowKey={(user) => user.id}
            columns={[
              {
                id: "user",
                header: "User",
                mobilePrimary: true,
                render: (user) => (
                  <>
                    <span className="rv-cell-primary">{displayName(user)}</span>
                    <span className="rv-cell-secondary">
                      {user.email ?? "No email on file"}
                      {user.email === userEmail ? " · you" : ""}
                    </span>
                  </>
                ),
              },
              {
                id: "role",
                header: "Role",
                render: (user) => <RoleBadge role={user.role} />,
              },
              {
                id: "notifications",
                header: "Notifications",
                render: (user) =>
                  user.email_enabled ? (
                    <Badge tone="info" Icon={Mail}>
                      {user.frequency ?? "instant"} email
                    </Badge>
                  ) : (
                    <Badge>In-app only</Badge>
                  ),
              },
              {
                id: "topics",
                header: "Topics",
                render: (user) =>
                  user.topics?.length ? (
                    <span className="rv-cell-secondary">
                      {user.topics.slice(0, 3).join(", ")}
                      {user.topics.length > 3 ? ` +${user.topics.length - 3}` : ""}
                    </span>
                  ) : (
                    <span className="rv-meta">All topics</span>
                  ),
              },
              {
                id: "created",
                header: "Created",
                render: (user) => (
                  <span className="rv-cell-secondary">{formatDate(user.created_at)}</span>
                ),
              },
              {
                id: "actions",
                header: "Actions",
                actions: true,
                render: (user) => (
                  <ActionMenu
                    label={`Actions for ${displayName(user)}`}
                    items={[
                      user.role === "admin"
                        ? {
                            id: "demote",
                            label: "Revoke admin access",
                            Icon: UserRound,
                            destructive: true,
                            disabled:
                              roleMutation.isPending || user.email === userEmail,
                            onSelect: () => setPendingRole({ user, role: "user" }),
                          }
                        : {
                            id: "promote",
                            label: "Make administrator",
                            Icon: ShieldCheck,
                            disabled: roleMutation.isPending,
                            onSelect: () => setPendingRole({ user, role: "admin" }),
                          },
                    ]}
                  />
                ),
              },
            ]}
            mobileActions={(user) =>
              user.email === userEmail && user.role === "admin" ? (
                <p className="rv-helper">
                  You cannot change your own administrator access.
                </p>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  block
                  onClick={() =>
                    setPendingRole({
                      user,
                      role: user.role === "admin" ? "user" : "admin",
                    })
                  }
                >
                  {user.role === "admin" ? "Revoke admin access" : "Make administrator"}
                </Button>
              )
            }
          />
          <Pagination
            page={query.data?.page ?? 1}
            pageSize={query.data?.page_size ?? PAGE_SIZE}
            total={query.data?.total ?? 0}
            totalPages={query.data?.total_pages ?? 1}
            onPageChange={setPage}
            itemLabel="users"
            busy={query.isFetching}
          />
        </>
      ) : hasFilters ? (
        <EmptyState
          title="No users match your filters"
          body="Try a different role or notification filter, or clear the search."
          Icon={Users}
          action={
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <EmptyState
          title="No users yet"
          body="Accounts appear here once people sign up or are invited to the workspace."
          Icon={Users}
        />
      )}

      <ConfirmDialog
        open={Boolean(pendingRole)}
        title={
          pendingRole?.role === "admin"
            ? "Grant administrator access?"
            : "Revoke administrator access?"
        }
        body={
          pendingRole?.role === "admin" ? (
            <>
              <p>
                {displayName(pendingRole.user)} will be able to manage sources, trigger
                crawls, view operational diagnostics and change other users&apos; roles.
              </p>
              <p className="rv-helper">This takes effect on their next request.</p>
            </>
          ) : (
            <p>
              {pendingRole ? displayName(pendingRole.user) : "This user"} will lose access
              to the operations console and keep normal product access.
            </p>
          )
        }
        confirmLabel={
          pendingRole?.role === "admin" ? "Grant admin access" : "Revoke admin access"
        }
        destructive={pendingRole?.role !== "admin"}
        loading={roleMutation.isPending}
        onCancel={() => setPendingRole(null)}
        onConfirm={() => {
          if (pendingRole) {
            roleMutation.mutate({
              userId: pendingRole.user.id,
              role: pendingRole.role,
            });
          }
        }}
      />
    </div>
  );
}
