import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useEmployeeSearch } from "@/hooks/useEmployees";
import { cn } from "@/lib/utils";

export interface EmployeeOption {
  id: number;
  label: string;
}

/** Searchable employee select (server-side search by name or code). */
export function EmployeeCombobox({
  value,
  onChange,
  placeholder = "Choose an employee",
  id,
}: {
  value: EmployeeOption | null;
  onChange: (value: EmployeeOption | null) => void;
  placeholder?: string;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const debounced = useDebouncedValue(search);
  const results = useEmployeeSearch(debounced, open);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className={cn("truncate", !value && "text-muted-foreground")}>{value?.label ?? placeholder}</span>
          <ChevronsUpDown className="opacity-50" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search name or code…" value={search} onValueChange={setSearch} />
          <CommandList>
            <CommandEmpty>{results.isFetching ? "Searching…" : "No active employee found."}</CommandEmpty>
            <CommandGroup>
              {(results.data?.data ?? []).map((employee) => {
                const label = `${employee.full_name} (${employee.employee_code})`;
                return (
                  <CommandItem
                    key={employee.id}
                    value={String(employee.id)}
                    onSelect={() => {
                      onChange({ id: employee.id, label });
                      setOpen(false);
                    }}
                  >
                    <Check className={cn(value?.id === employee.id ? "opacity-100" : "opacity-0")} aria-hidden />
                    <span className="truncate">{label}</span>
                    {employee.department_name && (
                      <span className="text-muted-foreground ml-auto text-xs">{employee.department_name}</span>
                    )}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
