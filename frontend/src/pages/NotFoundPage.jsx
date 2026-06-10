import { Button, Stack, Text, Title } from "@mantine/core";
import { useNavigate } from "react-router-dom";
import { useLanguage } from "../i18n/LanguageContext";

export default function NotFoundPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();

  return (
    <div className="auth-shell">
      <div className="auth-layout auth-layout-single">
        <div className="auth-panel auth-panel-centered">
          <div className="auth-card">
            <div className="auth-card-header">
              <p className="auth-card-kicker">404</p>
              <Title order={2}>{t("notFound.title")}</Title>
              <Text c="dimmed" size="sm" mt="xs">
                {t("notFound.detail")}
              </Text>
            </div>
            <Stack mt="lg">
              <Button
                radius="md"
                fullWidth
                onClick={() => navigate("/analytics", { replace: true })}
              >
                {t("notFound.goHome")}
              </Button>
            </Stack>
          </div>
        </div>
      </div>
    </div>
  );
}
