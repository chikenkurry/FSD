import { Injectable } from '@nestjs/common';
import { isUniqueViolation } from '../common/prisma-errors';
import { NewRound, RoundRecord, RoundRepository } from '../rounds/round.repository';
import { PrismaService } from './prisma.service';

@Injectable()
export class PrismaRoundRepository extends RoundRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  findById(id: string): Promise<RoundRecord | null> {
    return this.prisma.responseRound.findUnique({ where: { id } });
  }

  async create(round: NewRound): Promise<RoundRecord | null> {
    try {
      return await this.prisma.responseRound.create({ data: round });
    } catch (error) {
      if (isUniqueViolation(error)) return null;
      throw error;
    }
  }
}
