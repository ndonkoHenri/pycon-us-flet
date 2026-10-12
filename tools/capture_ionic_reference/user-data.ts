// Stand-in for Ionic's src/app/providers/user-data.ts (#66). processData never
// reads favourites; only filterSession does.

export class UserData {
  hasFavorite(_id: unknown): boolean {
    return false;
  }
}
