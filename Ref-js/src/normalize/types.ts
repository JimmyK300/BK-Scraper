import { z } from 'zod';

export const ItemKindSchema = z.enum(['lecture', 'assignment', 'quiz', 'notes', 'unknown']);
export type ItemKind = z.infer<typeof ItemKindSchema>;

export const NormalizedItemSchema = z.object({
  source: z.object({
    activityId: z.number().int().optional(),
    modType: z.string().optional(),
    url: z.string().url()
  }),
  title: z.string().min(1),
  kind: ItemKindSchema,
  url: z.string().url(),
  dueAt: z.string().datetime().optional(),
  dueRaw: z.string().optional()
});
export type NormalizedItem = z.infer<typeof NormalizedItemSchema>;

export const NormalizedSectionSchema = z.object({
  source: z.object({
    sectionId: z.string().optional(),
    sectionIndex: z.number().int().optional()
  }),
  title: z.string().min(1),
  items: z.array(NormalizedItemSchema)
});
export type NormalizedSection = z.infer<typeof NormalizedSectionSchema>;

export const NormalizedCourseSchema = z.object({
  source: z.object({
    baseUrl: z.string().url(),
    courseId: z.number().int(),
    scrapedAt: z.string().datetime()
  }),
  title: z.string().min(1),
  sections: z.array(NormalizedSectionSchema)
});
export type NormalizedCourse = z.infer<typeof NormalizedCourseSchema>;
