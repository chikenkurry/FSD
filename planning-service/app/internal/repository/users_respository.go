package repository

import (
	"context"
	"errors"
	"planning-service/app/internal/database"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrUserNotFound      = errors.New("user not found")
	ErrUsernameDuplicate = errors.New("username already taken")
)

type UserRepository struct {
	db *gorm.DB
}

func NewUserRepository(db *gorm.DB) *UserRepository {
	return &UserRepository{db: db}
}

// Create inserts a new user
func (r *UserRepository) Create(ctx context.Context, user *model.User) error {
	err := database.ContextDB(ctx, r.db).Create(user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrDuplicatedKey) {
			return ErrUsernameDuplicate
		}
		return err
	}
	return nil
}

// GetByID fetches a user by primary key
func (r *UserRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.User, error) {
	var user model.User
	err := database.ContextDB(ctx, r.db).First(&user, "id = ?", id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return &user, nil
}

// GetByIDWithRelations fetches a user and preloads their created plans and memberships
func (r *UserRepository) GetByIDWithRelations(ctx context.Context, id uuid.UUID) (*model.User, error) {
	var user model.User
	err := database.ContextDB(ctx, r.db).
		Preload("CreatedPlans").
		Preload("Memberships").
		First(&user, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return &user, nil
}



// Update replaces a user's username and email. An empty email clears it
// (email is optional; see migration 004).
func (r *UserRepository) Update(ctx context.Context, user *model.User) error {
	result := database.ContextDB(ctx, r.db).
		Model(&model.User{}).
		Where("id = ?", user.ID).
		Updates(map[string]interface{}{"username": user.Username, "email": user.Email})

	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrUserNotFound
	}
	return nil
}

// Delete removes a user by ID
func (r *UserRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := database.ContextDB(ctx, r.db).Delete(&model.User{}, "id = ?", id)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrUserNotFound
	}
	return nil
}