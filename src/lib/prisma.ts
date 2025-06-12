import { PrismaClient } from '@prisma/client';

// Ensure a singleton PrismaClient across hot reloads
const globalForPrisma = global as unknown as { prisma?: PrismaClient };

const prisma = globalForPrisma.prisma ?? new PrismaClient();
if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}

process.on('beforeExit', () => {
  prisma.$disconnect().catch(() => {
    // ignore errors on shutdown
  });
});

export default prisma;
