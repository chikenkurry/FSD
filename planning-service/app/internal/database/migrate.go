package database

import (
	"crypto/sha256"
	"embed"
	"fmt"
	"gorm.io/gorm"
	"regexp"
	"strings"
)

//go:embed migrations/*.sql
var migrations embed.FS

// Migrate applies immutable SQL under one PostgreSQL advisory transaction lock.
// Existing complete legacy schemas are adopted as baseline; partial schemas fail closed.
func Migrate(db *gorm.DB) error {
	return db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Exec("SELECT pg_advisory_xact_lock(92741014)").Error; err != nil {
			return err
		}
		if err := tx.Exec("CREATE TABLE IF NOT EXISTS planning_schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())").Error; err != nil {
			return err
		}
		files, err := migrations.ReadDir("migrations")
		if err != nil {
			return err
		}
		for _, file := range files {
			contents, err := migrations.ReadFile("migrations/" + file.Name())
			if err != nil {
				return err
			}
			checksum := fmt.Sprintf("%x", sha256.Sum256(contents))
			var prior struct{ Checksum string }
			if err := tx.Table("planning_schema_migrations").Where("name = ?", file.Name()).Find(&prior).Error; err != nil {
				return err
			}
			if prior.Checksum != "" {
				if prior.Checksum != checksum {
					return fmt.Errorf("migration %s changed after application", file.Name())
				}
				continue
			}
			if file.Name() == "001_baseline.sql" && tx.Migrator().HasTable("plans") {
				if err := verifyBaseline(tx, string(contents)); err != nil {
					return err
				}
			} else if err := tx.Exec(string(contents)).Error; err != nil {
				return fmt.Errorf("migration %s: %w", file.Name(), err)
			}
			if err := tx.Exec("INSERT INTO planning_schema_migrations(name,checksum) VALUES (?,?)", file.Name(), checksum).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

func verifyBaseline(tx *gorm.DB, sql string) error {
	tables := regexp.MustCompile(`(?s)CREATE TABLE public\.([a-z_]+) \((.*?)\);`).FindAllStringSubmatch(sql, -1)
	for _, table := range tables {
		var names []string
		if err := tx.Raw("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?", table[1]).Scan(&names).Error; err != nil {
			return err
		}
		known := map[string]bool{}
		for _, name := range names {
			known[name] = true
		}
		for _, line := range strings.Split(table[2], "\n") {
			fields := strings.Fields(line)
			if len(fields) == 0 {
				continue
			}
			if !known[fields[0]] {
				return fmt.Errorf("legacy baseline incomplete: %s.%s missing", table[1], fields[0])
			}
		}
	}
	return nil
}
