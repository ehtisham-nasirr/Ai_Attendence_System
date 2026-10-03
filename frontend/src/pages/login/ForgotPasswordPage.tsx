import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";

import { requestPasswordReset } from "@/api/generated/endpoints";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { showFormError } from "@/lib/forms";
import { forgotPasswordSchema, type ForgotPasswordValues } from "@/lib/schemas/auth";

export function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const form = useForm<ForgotPasswordValues>({ resolver: zodResolver(forgotPasswordSchema), defaultValues: { email: "" } });

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      setSent((await requestPasswordReset(values)).message);
    } catch (error) {
      showFormError(form, error);
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reset your password</CardTitle>
        <CardDescription>
          For FaceTrack accounts. Active Directory passwords are changed through IT.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {sent ? (
          <p role="status" className="text-sm">
            {sent}
          </p>
        ) : (
          <Form {...form}>
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" autoComplete="email" autoFocus {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
                Send reset link
              </Button>
            </form>
          </Form>
        )}
        <Link to="/login" className="text-primary block text-center text-sm hover:underline">
          Back to sign in
        </Link>
      </CardContent>
    </Card>
  );
}
