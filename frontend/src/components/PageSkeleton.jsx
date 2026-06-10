import { Box, Group, SimpleGrid, Skeleton, Stack } from "@mantine/core";

/**
 * Generic page loading skeleton — used as the Suspense fallback and for
 * per-page data loading states. Provides visual continuity while content loads.
 */
export default function PageSkeleton() {
  return (
    <Box p="xl" pt="lg">
      {/* Page header */}
      <Stack mb="xl" gap="xs">
        <Skeleton height={14} width={120} radius="sm" />
        <Skeleton height={28} width={240} radius="sm" />
      </Stack>

      {/* Summary cards row */}
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} mb="xl">
        {[1, 2, 3, 4].map((i) => (
          <Box key={i} p="md" style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
            <Skeleton height={12} width="60%" mb="sm" radius="sm" />
            <Skeleton height={24} width="80%" radius="sm" />
          </Box>
        ))}
      </SimpleGrid>

      {/* Main content area */}
      <SimpleGrid cols={{ base: 1, md: 2 }} mb="xl">
        <Box p="md" style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
          <Skeleton height={14} width={160} mb="md" radius="sm" />
          <Stack gap="sm">
            {[1, 2, 3, 4, 5].map((i) => (
              <Group key={i} justify="space-between">
                <Skeleton height={12} width="45%" radius="sm" />
                <Skeleton height={12} width="20%" radius="sm" />
              </Group>
            ))}
          </Stack>
        </Box>
        <Box p="md" style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
          <Skeleton height={14} width={160} mb="md" radius="sm" />
          <Skeleton height={160} radius="sm" />
        </Box>
      </SimpleGrid>
    </Box>
  );
}
