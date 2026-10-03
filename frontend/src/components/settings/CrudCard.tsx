import { Pencil, Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface CrudColumn<T> {
  header: string;
  cell: (row: T) => ReactNode;
}

/** Small reference lists on the Settings screen (locations, departments, shifts, holidays). */
export function CrudCard<T extends { id: number }>({
  title,
  description,
  rows,
  columns,
  isLoading,
  error,
  onRetry,
  addLabel,
  emptyText,
  onAdd,
  onEdit,
  onDelete,
  toolbar,
}: {
  title: string;
  description?: string;
  rows: T[] | undefined;
  columns: CrudColumn<T>[];
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  addLabel: string;
  emptyText: string;
  onAdd: () => void;
  onEdit?: (row: T) => void;
  onDelete: (row: T) => void;
  toolbar?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
          <Button size="sm" onClick={onAdd}>
            <Plus aria-hidden /> {addLabel}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorState error={error} onRetry={onRetry} />
        ) : isLoading ? (
          <Skeleton className="h-24" />
        ) : !rows || rows.length === 0 ? (
          <p className="text-muted-foreground py-6 text-center text-sm">{emptyText}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((column) => (
                  <TableHead key={column.header}>{column.header}</TableHead>
                ))}
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  {columns.map((column) => (
                    <TableCell key={column.header}>{column.cell(row)}</TableCell>
                  ))}
                  <TableCell className="text-right">
                    {onEdit && (
                      <Button variant="ghost" size="icon" className="size-8" aria-label="Edit" onClick={() => onEdit(row)}>
                        <Pencil />
                      </Button>
                    )}
                    <Button variant="ghost" size="icon" className="size-8" aria-label="Delete" onClick={() => onDelete(row)}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
